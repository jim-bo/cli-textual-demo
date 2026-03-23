"""Integration tests for native agent tools using a real LLM via OpenRouter.

All tests are skipped unless OPENROUTER_API_KEY is set.  They exercise the full
run_manager_pipeline path — real model, real tool execution, real event stream —
and assert that the LLM correctly invokes tools and incorporates their output.
"""
import os
import asyncio
import pytest

from cli_textual.agents.orchestrators import manager_agent, run_manager_pipeline
from cli_textual.core.chat_events import (
    AgentToolStart, AgentToolOutput, AgentStreamChunk, AgentComplete,
    AgentRequiresUserInput,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SKIP_NO_KEY = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY required for integration tests",
)


async def collect_pipeline(pipeline, input_queue, auto_respond=None) -> list:
    """Drain pipeline events, optionally responding to AgentRequiresUserInput."""
    events = []
    async for event in pipeline:
        events.append(event)
        if isinstance(event, AgentRequiresUserInput) and auto_respond is not None:
            await input_queue.put(auto_respond)
    return events


def text_from(events) -> str:
    return "".join(e.text for e in events if isinstance(e, AgentStreamChunk))


def tool_started(events, name: str) -> bool:
    return any(isinstance(e, AgentToolStart) and e.tool_name == name for e in events)


def tool_output_contains(events, name: str, substring: str) -> bool:
    return any(
        isinstance(e, AgentToolOutput) and e.tool_name == name and substring in e.content
        for e in events
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@SKIP_NO_KEY
@pytest.mark.asyncio
async def test_bash_exec_e2e():
    """LLM should call bash_exec and incorporate the output in its response."""
    input_queue = asyncio.Queue()
    pipeline = run_manager_pipeline(
        "Run the shell command 'echo hello world' and tell me what it outputs.",
        input_queue,
    )
    events = await collect_pipeline(pipeline, input_queue)

    assert tool_started(events, "bash_exec"), "Expected bash_exec tool call"
    assert tool_output_contains(events, "bash_exec", "hello world"), \
        "Expected 'hello world' in bash_exec output"
    full_text = text_from(events)
    assert "hello world" in full_text.lower(), \
        f"LLM response did not mention 'hello world'. Got: {full_text[:300]}"
    assert isinstance(events[-1], AgentComplete)


@SKIP_NO_KEY
@pytest.mark.asyncio
async def test_read_file_e2e():
    """LLM should call read_file when asked to inspect a file."""
    input_queue = asyncio.Queue()
    pipeline = run_manager_pipeline(
        "Read the file src/cli_textual/core/chat_events.py and tell me what events are defined.",
        input_queue,
    )
    events = await collect_pipeline(pipeline, input_queue)

    assert tool_started(events, "read_file"), "Expected read_file tool call"
    full_text = text_from(events)
    # The file contains ChatEvent / AgentComplete — the LLM should mention at least one
    assert any(keyword in full_text for keyword in ["ChatEvent", "AgentComplete", "event"]), \
        f"LLM response didn't mention events. Got: {full_text[:300]}"
    assert isinstance(events[-1], AgentComplete)


@SKIP_NO_KEY
@pytest.mark.asyncio
async def test_web_fetch_e2e():
    """LLM should call web_fetch when asked to retrieve a URL."""
    input_queue = asyncio.Queue()
    pipeline = run_manager_pipeline(
        "Fetch the URL https://httpbin.org/json and tell me what the JSON contains.",
        input_queue,
    )
    events = await collect_pipeline(pipeline, input_queue)

    assert tool_started(events, "web_fetch"), "Expected web_fetch tool call"
    # httpbin.org/json returns {"slideshow": ...}
    assert tool_output_contains(events, "web_fetch", "slideshow") or \
        tool_output_contains(events, "web_fetch", "200"), \
        "Expected HTTP response in web_fetch output"
    assert isinstance(events[-1], AgentComplete)


@SKIP_NO_KEY
@pytest.mark.asyncio
async def test_select_then_bash_e2e():
    """LLM should use ask_user_to_select first, then run bash_exec with the chosen command."""
    input_queue = asyncio.Queue()
    pipeline = run_manager_pipeline(
        "Let me pick a shell command from a list, then run it and show me the output.",
        input_queue,
    )
    events = await collect_pipeline(pipeline, input_queue, auto_respond="echo chosen_value")

    assert any(isinstance(e, AgentRequiresUserInput) for e in events), \
        "Expected a selection prompt"
    assert tool_started(events, "bash_exec"), \
        "Expected bash_exec to be called after selection"
    full_text = text_from(events)
    assert full_text, "Expected some text response"
    assert isinstance(events[-1], AgentComplete)
