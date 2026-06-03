"""Tests for the write_file and edit_file tools.

Covers the pure functions (cli_textual.tools.{write_file,edit_file}) including
the ported Aider forgiving matcher, plus the manager.py wrappers' event
lifecycle (called directly with a mock ctx, like test_agent_tools.py).
"""
import asyncio

import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.timeout(5)

from cli_textual.agents.manager import edit_file as edit_file_wrapper
from cli_textual.agents.manager import write_file as write_file_wrapper
from cli_textual.core.chat_events import (
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
    ChatDeps,
)
from cli_textual.tools.base import ToolResult
from cli_textual.tools.edit_file import edit_file
from cli_textual.tools.write_file import write_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx() -> tuple:
    event_queue: asyncio.Queue = asyncio.Queue()
    input_queue: asyncio.Queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)
    ctx = MagicMock()
    ctx.deps = deps
    return ctx, event_queue


async def drain(q: asyncio.Queue) -> list:
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


# ---------------------------------------------------------------------------
# write_file (pure)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_creates_new_file(tmp_path):
    result = await write_file("hello.py", "print('hi')\n", workspace_root=tmp_path)
    assert isinstance(result, ToolResult)
    assert not result.is_error
    assert (tmp_path / "hello.py").read_text() == "print('hi')\n"
    assert "Created" in result.output


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path):
    result = await write_file("a/b/c.txt", "deep", workspace_root=tmp_path)
    assert not result.is_error
    assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"


@pytest.mark.asyncio
async def test_write_file_overwrites_existing(tmp_path):
    (tmp_path / "f.txt").write_text("old")
    result = await write_file("f.txt", "new", workspace_root=tmp_path)
    assert not result.is_error
    assert "Updated" in result.output
    assert (tmp_path / "f.txt").read_text() == "new"


@pytest.mark.asyncio
async def test_write_file_rejects_path_outside_workspace(tmp_path):
    result = await write_file("../escape.txt", "x", workspace_root=tmp_path)
    assert result.is_error
    assert "outside workspace" in result.output
    assert not (tmp_path.parent / "escape.txt").exists()


# ---------------------------------------------------------------------------
# edit_file (pure) — exact semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_unique_replace(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n")
    result = await edit_file("m.py", "return 1", "return 2", workspace_root=tmp_path)
    assert not result.is_error
    assert f.read_text() == "def foo():\n    return 2\n"


@pytest.mark.asyncio
async def test_edit_file_not_found_errors(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\n")
    result = await edit_file("m.py", "nonexistent text", "x", workspace_root=tmp_path)
    assert result.is_error
    assert "not found" in result.output
    assert f.read_text() == "a = 1\n"  # unchanged


@pytest.mark.asyncio
async def test_edit_file_multiple_matches_errors(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\nx = 1\n")
    result = await edit_file("m.py", "x = 1", "x = 2", workspace_root=tmp_path)
    assert result.is_error
    assert "2 matches" in result.output
    assert f.read_text() == "x = 1\nx = 1\n"  # unchanged


@pytest.mark.asyncio
async def test_edit_file_replace_all(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\nx = 1\nx = 1\n")
    result = await edit_file("m.py", "x = 1", "x = 2", replace_all=True, workspace_root=tmp_path)
    assert not result.is_error
    assert f.read_text() == "x = 2\nx = 2\nx = 2\n"


@pytest.mark.asyncio
async def test_edit_file_delete_text(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("keep\nremove me\nkeep\n")
    result = await edit_file("m.py", "remove me\n", "", workspace_root=tmp_path)
    assert not result.is_error
    assert f.read_text() == "keep\nkeep\n"


@pytest.mark.asyncio
async def test_edit_file_identical_strings_errors(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\n")
    result = await edit_file("m.py", "a = 1", "a = 1", workspace_root=tmp_path)
    assert result.is_error
    assert "identical" in result.output


@pytest.mark.asyncio
async def test_edit_file_empty_old_string_errors(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\n")
    result = await edit_file("m.py", "", "x", workspace_root=tmp_path)
    assert result.is_error
    assert "empty" in result.output
    assert f.read_text() == "a = 1\n"  # unchanged


@pytest.mark.asyncio
async def test_edit_file_non_utf8_errors(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\xff\xfe\x00bad bytes")
    result = await edit_file("bin.dat", "bad", "good", workspace_root=tmp_path)
    assert result.is_error
    assert "UTF-8" in result.output
    assert f.read_bytes() == b"\xff\xfe\x00bad bytes"  # untouched


@pytest.mark.asyncio
async def test_edit_file_missing_file_errors(tmp_path):
    result = await edit_file("ghost.py", "a", "b", workspace_root=tmp_path)
    assert result.is_error
    assert "not found" in result.output


@pytest.mark.asyncio
async def test_edit_file_rejects_path_outside_workspace(tmp_path):
    result = await edit_file("../escape.py", "a", "b", workspace_root=tmp_path)
    assert result.is_error
    assert "outside workspace" in result.output


# ---------------------------------------------------------------------------
# edit_file (pure) — forgiving matcher (ported from Aider)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_tolerates_leading_whitespace_drift(tmp_path):
    """old_string given with no indentation still matches an indented block."""
    f = tmp_path / "m.py"
    f.write_text("class A:\n    def foo(self):\n        return 1\n")
    # Model supplies the body without the 8-space indentation.
    result = await edit_file(
        "m.py",
        "def foo(self):\n    return 1",
        "def foo(self):\n    return 99",
        workspace_root=tmp_path,
    )
    assert not result.is_error, result.output
    assert "return 99" in f.read_text()


@pytest.mark.asyncio
async def test_edit_file_handles_dotdotdot_elision(tmp_path):
    """`...` between anchors lets the model elide the unchanged middle."""
    f = tmp_path / "m.py"
    f.write_text("start\nline1\nline2\nline3\nend\n")
    result = await edit_file(
        "m.py",
        "start\n...\nend",
        "START\n...\nEND",
        workspace_root=tmp_path,
    )
    assert not result.is_error, result.output
    text = f.read_text()
    assert text.startswith("START")
    assert "END" in text
    assert "line2" in text  # middle preserved


# ---------------------------------------------------------------------------
# Wrapper event lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_file_wrapper_emits_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx, event_queue = make_ctx()
    await write_file_wrapper(ctx, path="new.txt", content="hi")
    events = await drain(event_queue)
    types = [type(e) for e in events]
    assert AgentToolStart in types
    assert AgentToolOutput in types
    assert AgentToolEnd in types
    start = next(i for i, e in enumerate(events) if isinstance(e, AgentToolStart))
    out = next(i for i, e in enumerate(events) if isinstance(e, AgentToolOutput))
    end = next(i for i, e in enumerate(events) if isinstance(e, AgentToolEnd))
    assert start < out < end
    assert (tmp_path / "new.txt").read_text() == "hi"


@pytest.mark.asyncio
async def test_edit_file_wrapper_emits_lifecycle_and_error_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "e.txt").write_text("a = 1\n")
    ctx, event_queue = make_ctx()
    # No-match edit → wrapper should still emit lifecycle, with error status.
    await edit_file_wrapper(ctx, path="e.txt", old_string="zzz", new_string="b")
    events = await drain(event_queue)
    end = next(e for e in events if isinstance(e, AgentToolEnd))
    assert end.result == "error"
    output = next(e for e in events if isinstance(e, AgentToolOutput))
    assert output.is_error
