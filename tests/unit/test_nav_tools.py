"""Tests for the navigation/planning tools: grep, glob, todo_write."""
import pytest

from cli_textual.tools.glob_tool import glob
from cli_textual.tools.grep import grep
from cli_textual.tools.todo_write import todo_write

pytestmark = pytest.mark.timeout(5)


def _tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "pkg" / "b.py").write_text("x = 2\n# foo reference\n")
    (tmp_path / "README.md").write_text("foo in docs\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "c.py").write_text("foo in vcs\n")  # must be skipped
    return tmp_path


# --- grep ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grep_finds_matches(tmp_path):
    _tree(tmp_path)
    r = await grep("foo", workspace_root=tmp_path)
    assert not r.is_error
    assert "pkg/a.py:1:" in r.output
    assert "pkg/b.py:2:" in r.output
    assert "README.md:1:" in r.output


@pytest.mark.asyncio
async def test_grep_skips_vcs_dirs(tmp_path):
    _tree(tmp_path)
    r = await grep("foo", workspace_root=tmp_path)
    assert ".git" not in r.output


@pytest.mark.asyncio
async def test_grep_no_match(tmp_path):
    _tree(tmp_path)
    r = await grep("nonexistent_zzz", workspace_root=tmp_path)
    assert not r.is_error
    assert "No matches" in r.output


@pytest.mark.asyncio
async def test_grep_invalid_regex(tmp_path):
    _tree(tmp_path)
    r = await grep("(unclosed", workspace_root=tmp_path)
    assert r.is_error
    assert "invalid regex" in r.output


@pytest.mark.asyncio
async def test_grep_jailed(tmp_path):
    _tree(tmp_path)
    r = await grep("foo", path="../..", workspace_root=tmp_path)
    assert r.is_error
    assert "outside workspace" in r.output


# --- glob ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_glob_finds_files(tmp_path):
    _tree(tmp_path)
    r = await glob("**/*.py", workspace_root=tmp_path)
    assert not r.is_error
    assert "pkg/a.py" in r.output and "pkg/b.py" in r.output


@pytest.mark.asyncio
async def test_glob_skips_vcs(tmp_path):
    _tree(tmp_path)
    r = await glob("**/*.py", workspace_root=tmp_path)
    assert ".git" not in r.output


@pytest.mark.asyncio
async def test_glob_no_match(tmp_path):
    _tree(tmp_path)
    r = await glob("**/*.rs", workspace_root=tmp_path)
    assert not r.is_error
    assert "No files" in r.output


@pytest.mark.asyncio
async def test_glob_jailed(tmp_path):
    _tree(tmp_path)
    r = await glob("*", path="/etc", workspace_root=tmp_path)
    assert r.is_error
    assert "outside workspace" in r.output


# --- todo_write ------------------------------------------------------------

@pytest.mark.asyncio
async def test_todo_write_renders_checklist():
    r = await todo_write([
        {"content": "read code", "status": "completed"},
        {"content": "fix bug", "status": "in_progress"},
        {"content": "run tests", "status": "pending"},
    ])
    assert not r.is_error
    assert "[x] read code" in r.output
    assert "[~] fix bug" in r.output
    assert "[ ] run tests" in r.output
    assert "(1/3 complete)" in r.output


@pytest.mark.asyncio
async def test_todo_write_rejects_empty():
    r = await todo_write([])
    assert r.is_error


@pytest.mark.asyncio
async def test_todo_write_rejects_bad_status():
    r = await todo_write([{"content": "x", "status": "bogus"}])
    assert r.is_error
    assert "invalid" in r.output


@pytest.mark.asyncio
async def test_todo_write_rejects_missing_content():
    r = await todo_write([{"status": "pending"}])
    assert r.is_error
    assert "content" in r.output


# --- registration ----------------------------------------------------------

def test_nav_tools_registered_and_safe():
    """grep/glob/todo_write are built-in and available even in SAFE_MODE."""
    from cli_textual.agents.manager import _BUILTIN_TOOLS, _UNSAFE_TOOLS
    for name in ("grep", "glob", "todo_write"):
        assert name in _BUILTIN_TOOLS
        assert name not in _UNSAFE_TOOLS  # read-only, safe to expose
