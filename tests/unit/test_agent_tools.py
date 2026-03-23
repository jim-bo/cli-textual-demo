"""Unit tests for the native manager_agent tools (bash_exec, read_file, web_fetch).

Tools are called directly — the @agent.tool decorator registers them but returns
the original function unchanged, so they can be invoked as plain async functions.
A minimal mock RunContext carrying real asyncio.Queues stands in for the live
pydantic-ai context.
"""
import asyncio
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from cli_textual.core.chat_events import (
    ChatDeps, AgentToolStart, AgentToolEnd, AgentToolOutput,
)
from cli_textual.agents.orchestrators import bash_exec, read_file, web_fetch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx() -> tuple:
    """Return (ctx, event_queue) backed by real asyncio.Queues."""
    event_queue: asyncio.Queue = asyncio.Queue()
    input_queue: asyncio.Queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)
    ctx = MagicMock()
    ctx.deps = deps
    return ctx, event_queue


async def drain(q: asyncio.Queue) -> list:
    """Return all items currently in the queue without blocking."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


# ---------------------------------------------------------------------------
# bash_exec
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_exec_captures_output():
    ctx, event_queue = make_ctx()
    result = await bash_exec(ctx, command="echo hello")
    assert "hello" in result
    assert "Exit code: 0" in result


@pytest.mark.asyncio
async def test_bash_exec_emits_lifecycle_events():
    ctx, event_queue = make_ctx()
    await bash_exec(ctx, command="echo lifecycle")
    events = await drain(event_queue)

    types = [type(e) for e in events]
    assert AgentToolStart in types
    assert AgentToolOutput in types
    assert AgentToolEnd in types

    # Order must be Start → Output → End
    start_idx = next(i for i, e in enumerate(events) if isinstance(e, AgentToolStart))
    output_idx = next(i for i, e in enumerate(events) if isinstance(e, AgentToolOutput))
    end_idx = next(i for i, e in enumerate(events) if isinstance(e, AgentToolEnd))
    assert start_idx < output_idx < end_idx


@pytest.mark.asyncio
async def test_bash_exec_output_event_contains_text():
    ctx, event_queue = make_ctx()
    await bash_exec(ctx, command="echo unique_marker_xyz")
    events = await drain(event_queue)
    output_events = [e for e in events if isinstance(e, AgentToolOutput)]
    combined = "".join(e.content for e in output_events)
    assert "unique_marker_xyz" in combined


@pytest.mark.asyncio
async def test_bash_exec_nonzero_exit_code():
    ctx, _ = make_ctx()
    result = await bash_exec(ctx, command="sh -c 'exit 42'")
    assert "42" in result


@pytest.mark.asyncio
async def test_bash_exec_invalid_command_does_not_raise():
    ctx, _ = make_ctx()
    # A command that doesn't exist — should return a non-empty string, not raise
    result = await bash_exec(ctx, command="__nonexistent_command_xyz__")
    assert result


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_returns_contents():
    ctx, _ = make_ctx()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line one\nline two\nline three\n")
        tmp_path = f.name
    try:
        result = await read_file(ctx, path=tmp_path)
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_read_file_line_range():
    ctx, _ = make_ctx()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("alpha\nbeta\ngamma\ndelta\n")
        tmp_path = f.name
    try:
        result = await read_file(ctx, path=tmp_path, start_line=2, end_line=3)
        assert "beta" in result
        assert "gamma" in result
        assert "alpha" not in result
        assert "delta" not in result
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_read_file_emits_lifecycle_events():
    ctx, event_queue = make_ctx()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("content")
        tmp_path = f.name
    try:
        await read_file(ctx, path=tmp_path)
        events = await drain(event_queue)
        types = [type(e) for e in events]
        assert AgentToolStart in types
        assert AgentToolOutput in types
        assert AgentToolEnd in types
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_read_file_missing_returns_error_string():
    ctx, event_queue = make_ctx()
    result = await read_file(ctx, path="/nonexistent/path/file_xyz.txt")
    assert "error" in result.lower() or "Error" in result
    # Must also emit an error output event
    events = await drain(event_queue)
    error_events = [e for e in events if isinstance(e, AgentToolOutput) and e.is_error]
    assert error_events


# ---------------------------------------------------------------------------
# web_fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_fetch_returns_body():
    ctx, _ = make_ctx()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"key": "value"}'

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("cli_textual.agents.orchestrators.httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch(ctx, url="https://example.com/api")

    assert "200" in result
    assert "value" in result


@pytest.mark.asyncio
async def test_web_fetch_emits_lifecycle_events():
    ctx, event_queue = make_ctx()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "body content"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("cli_textual.agents.orchestrators.httpx.AsyncClient", return_value=mock_client):
        await web_fetch(ctx, url="https://example.com")

    events = await drain(event_queue)
    types = [type(e) for e in events]
    assert AgentToolStart in types
    assert AgentToolOutput in types
    assert AgentToolEnd in types


@pytest.mark.asyncio
async def test_web_fetch_network_error_returns_error_string():
    ctx, event_queue = make_ctx()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("cli_textual.agents.orchestrators.httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch(ctx, url="https://unreachable.example")

    assert "error" in result.lower() or "Error" in result
    events = await drain(event_queue)
    error_events = [e for e in events if isinstance(e, AgentToolOutput) and e.is_error]
    assert error_events
