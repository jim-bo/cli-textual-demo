"""Tests for safe-mode protections: path jailing, SSRF blocking, conditional bash."""
import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from cli_textual.tools.read_file import read_file
from cli_textual.tools.web_fetch import web_fetch, _is_url_safe


# ---------------------------------------------------------------------------
# read_file — path jailing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_blocks_path_traversal(tmp_path):
    result = await read_file("../../etc/passwd", workspace_root=tmp_path)
    assert result.is_error
    assert "access denied" in result.output


@pytest.mark.asyncio
async def test_read_file_blocks_absolute_escape(tmp_path):
    result = await read_file("/etc/passwd", workspace_root=tmp_path)
    assert result.is_error
    assert "access denied" in result.output


@pytest.mark.asyncio
async def test_read_file_allows_workspace_files(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")
    result = await read_file("hello.txt", workspace_root=tmp_path)
    assert not result.is_error
    assert "hello world" in result.output


# ---------------------------------------------------------------------------
# web_fetch — SSRF protection
# ---------------------------------------------------------------------------

def test_is_url_safe_blocks_private_ip():
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
    assert "blocked host" in result.output or "private/internal" in result.output


def test_is_url_safe_blocks_aws_metadata_ip():
    err = _is_url_safe("http://169.254.169.254/latest/meta-data/")
    assert err is not None
    assert "blocked host" in err


def test_is_url_safe_blocks_azure_wireserver():
    err = _is_url_safe("http://168.63.129.16/")
    assert err is not None
    assert "blocked host" in err


# ---------------------------------------------------------------------------
# manager agent — conditional bash_exec
# ---------------------------------------------------------------------------

@pytest.fixture
def _reload_manager():
    """Reload manager module before and after the test for clean state."""
    import cli_textual.agents.manager as mgr
    original = os.environ.get("SAFE_MODE")
    yield mgr
    # Restore original state
    if original is None:
        os.environ.pop("SAFE_MODE", None)
    else:
        os.environ["SAFE_MODE"] = original
    importlib.reload(mgr)


def test_safe_mode_excludes_bash(monkeypatch, _reload_manager):
    mgr = _reload_manager
    monkeypatch.setenv("SAFE_MODE", "1")
    importlib.reload(mgr)
    tool_names = [name for name in mgr.manager_agent._function_toolset.tools]
    assert "bash_exec" not in tool_names


def test_normal_mode_includes_bash(monkeypatch, _reload_manager):
    mgr = _reload_manager
    monkeypatch.delenv("SAFE_MODE", raising=False)
    importlib.reload(mgr)
    tool_names = [name for name in mgr.manager_agent._function_toolset.tools]
    assert "bash_exec" in tool_names
