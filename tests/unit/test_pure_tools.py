"""Tests for pure tool functions in cli_textual.tools (TUI-independent)."""
import pytest
import tempfile
from unittest.mock import patch, AsyncMock
from cli_textual.tools import bash_exec, read_file, web_fetch
from cli_textual.tools.base import ToolResult


@pytest.mark.asyncio
async def test_bash_exec_captures_output():
    result = await bash_exec("echo hello")
    assert isinstance(result, ToolResult)
    assert "hello" in result.output
    assert result.exit_code == 0
    assert not result.is_error


@pytest.mark.asyncio
async def test_bash_exec_nonzero_exit():
    result = await bash_exec("exit 42")
    assert result.exit_code == 42
    assert not result.is_error


@pytest.mark.asyncio
async def test_bash_exec_invalid_command():
    result = await bash_exec("this_command_does_not_exist_xyz")
    assert isinstance(result, ToolResult)
    # Should complete without raising


@pytest.mark.asyncio
async def test_read_file_returns_contents():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        f.flush()
        result = await read_file(f.name)
    assert "line1" in result.output
    assert "line2" in result.output
    assert not result.is_error


@pytest.mark.asyncio
async def test_read_file_line_range():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("a\nb\nc\nd\n")
        f.flush()
        result = await read_file(f.name, start_line=2, end_line=3)
    assert "b" in result.output
    assert "c" in result.output
    assert "a" not in result.output


@pytest.mark.asyncio
async def test_read_file_missing():
    result = await read_file("/nonexistent/path/xyz.txt")
    assert result.is_error
    assert "Error" in result.output


@pytest.mark.asyncio
async def test_web_fetch_returns_body():
    mock_response = AsyncMock()
    mock_response.text = '{"key": "value"}'
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cli_textual.tools.web_fetch.httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com")
    assert "200" in result.output
    assert "value" in result.output
    assert not result.is_error


@pytest.mark.asyncio
async def test_web_fetch_network_error():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cli_textual.tools.web_fetch.httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://unreachable.invalid")
    assert result.is_error
    assert "Connection refused" in result.output
