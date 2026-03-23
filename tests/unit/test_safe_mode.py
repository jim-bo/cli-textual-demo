"""Tests for safe-mode protections: path jailing, SSRF blocking, conditional bash."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from cli_textual.tools.read_file import read_file
from cli_textual.tools.web_fetch import web_fetch, _is_url_safe


# ---------------------------------------------------------------------------
# read_file — path jailing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_blocks_path_traversal():
    workspace = Path(tempfile.mkdtemp())
    result = await read_file("../../etc/passwd", workspace_root=workspace)
    assert result.is_error
    assert "access denied" in result.output


@pytest.mark.asyncio
async def test_read_file_blocks_absolute_escape():
    workspace = Path(tempfile.mkdtemp())
    result = await read_file("/etc/passwd", workspace_root=workspace)
    assert result.is_error
    assert "access denied" in result.output


@pytest.mark.asyncio
async def test_read_file_allows_workspace_files():
    workspace = Path(tempfile.mkdtemp())
    test_file = workspace / "hello.txt"
    test_file.write_text("hello world")
    result = await read_file("hello.txt", workspace_root=workspace)
    assert not result.is_error
    assert "hello world" in result.output


# ---------------------------------------------------------------------------
# web_fetch — SSRF protection
# ---------------------------------------------------------------------------

def test_is_url_safe_blocks_private_ip():
    # 169.254.x.x is link-local
    with patch("cli_textual.tools.web_fetch.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("169.254.169.254", 0))]
        err = _is_url_safe("http://metadata.example.com/latest")
    assert err is not None
    assert "private/internal" in err


def test_is_url_safe_blocks_localhost():
    with patch("cli_textual.tools.web_fetch.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 0))]
        err = _is_url_safe("http://localhost:8080")
    assert err is not None
    assert "private/internal" in err


def test_is_url_safe_blocks_metadata_host():
    err = _is_url_safe("http://metadata.google.internal/computeMetadata/v1/")
    assert err is not None
    assert "blocked host" in err


def test_is_url_safe_blocks_bad_scheme():
    err = _is_url_safe("file:///etc/passwd")
    assert err is not None
    assert "unsupported scheme" in err


def test_is_url_safe_allows_public_url():
    with patch("cli_textual.tools.web_fetch.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        err = _is_url_safe("https://example.com")
    assert err is None


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_ip():
    with patch("cli_textual.tools.web_fetch.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("169.254.169.254", 0))]
        result = await web_fetch("http://169.254.169.254/latest/meta-data/")
    assert result.is_error
    assert "private/internal" in result.output


# ---------------------------------------------------------------------------
# manager agent — conditional bash_exec
# ---------------------------------------------------------------------------

def test_safe_mode_excludes_bash(monkeypatch):
    monkeypatch.setenv("SAFE_MODE", "1")
    # Re-import to trigger rebuild with SAFE_MODE=1
    import importlib
    import cli_textual.agents.manager as mgr
    importlib.reload(mgr)
    tool_names = [name for name in mgr.manager_agent._function_toolset.tools]
    assert "bash_exec" not in tool_names
    # Restore
    monkeypatch.delenv("SAFE_MODE")
    importlib.reload(mgr)


def test_normal_mode_includes_bash(monkeypatch):
    monkeypatch.delenv("SAFE_MODE", raising=False)
    import importlib
    import cli_textual.agents.manager as mgr
    importlib.reload(mgr)
    tool_names = [name for name in mgr.manager_agent._function_toolset.tools]
    assert "bash_exec" in tool_names
