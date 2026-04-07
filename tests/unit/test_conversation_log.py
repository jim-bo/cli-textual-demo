"""Tests for cli_textual.core.conversation_log.ConversationLogger."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_textual.core.chat_events import (
    AgentComplete,
    AgentStreamChunk,
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
)
from cli_textual.core.conversation_log import (
    ConversationLogger,
    default_log_path,
)

pytestmark = pytest.mark.timeout(5)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_session_start_and_end_markers(tmp_path):
    log_file = tmp_path / "log.jsonl"
    logger = ConversationLogger(log_file, session_id="abc-123")
    logger.close()

    rows = _read_jsonl(log_file)
    assert rows[0]["kind"] == "session_start"
    assert rows[0]["session_id"] == "abc-123"
    assert rows[-1]["kind"] == "session_end"
    for r in rows:
        assert "ts" in r


def test_log_user_message(tmp_path):
    log_file = tmp_path / "log.jsonl"
    with ConversationLogger(log_file, session_id="s") as logger:
        logger.log_user_message("hello agent")

    rows = _read_jsonl(log_file)
    user_rows = [r for r in rows if r["kind"] == "user_message"]
    assert len(user_rows) == 1
    assert user_rows[0]["text"] == "hello agent"


def test_log_user_command(tmp_path):
    log_file = tmp_path / "log.jsonl"
    with ConversationLogger(log_file, session_id="s") as logger:
        logger.log_user_command("/tools", [])
        logger.log_user_command("/head", ["README.md", "20"])

    rows = _read_jsonl(log_file)
    cmd_rows = [r for r in rows if r["kind"] == "user_command"]
    assert [(r["name"], r["args"]) for r in cmd_rows] == [
        ("/tools", []),
        ("/head", ["README.md", "20"]),
    ]


def test_log_event_serializes_dataclass_chat_events(tmp_path):
    log_file = tmp_path / "log.jsonl"
    with ConversationLogger(log_file, session_id="s") as logger:
        logger.log_event(AgentToolStart(tool_name="bash_exec", args={"command": "ls"}))
        logger.log_event(
            AgentToolOutput(tool_name="bash_exec", content="file1\nfile2", is_error=False)
        )
        logger.log_event(AgentToolEnd(tool_name="bash_exec", result="ok"))
        logger.log_event(AgentStreamChunk(text="Here are "))
        logger.log_event(AgentStreamChunk(text="the files."))

    rows = _read_jsonl(log_file)
    kinds = [r["kind"] for r in rows]
    assert "event:AgentToolStart" in kinds
    assert "event:AgentToolOutput" in kinds
    assert "event:AgentToolEnd" in kinds
    assert kinds.count("event:AgentStreamChunk") == 2

    start = next(r for r in rows if r["kind"] == "event:AgentToolStart")
    assert start["tool_name"] == "bash_exec"
    assert start["args"] == {"command": "ls"}

    output = next(r for r in rows if r["kind"] == "event:AgentToolOutput")
    assert output["content"] == "file1\nfile2"
    assert output["is_error"] is False


def test_log_event_handles_agent_complete_with_unserializable_history(tmp_path):
    """AgentComplete may carry pydantic-ai ModelMessage objects that won't
    cleanly JSON-serialize. The logger should fall back to repr() per item
    instead of crashing or dropping the line.
    """
    log_file = tmp_path / "log.jsonl"

    class _FakeMessage:
        def __repr__(self) -> str:
            return "FakeMessage(role='assistant', content='hi')"

    with ConversationLogger(log_file, session_id="s") as logger:
        logger.log_event(AgentComplete(new_history=[_FakeMessage(), _FakeMessage()]))

    rows = _read_jsonl(log_file)
    complete = next(r for r in rows if r["kind"] == "event:AgentComplete")
    assert isinstance(complete["new_history"], list)
    assert all("FakeMessage" in m for m in complete["new_history"])


def test_log_event_handles_agent_complete_with_none_history(tmp_path):
    log_file = tmp_path / "log.jsonl"
    with ConversationLogger(log_file, session_id="s") as logger:
        logger.log_event(AgentComplete(new_history=None))

    rows = _read_jsonl(log_file)
    complete = next(r for r in rows if r["kind"] == "event:AgentComplete")
    assert complete["new_history"] in (None, [])


def test_close_is_idempotent(tmp_path):
    log_file = tmp_path / "log.jsonl"
    logger = ConversationLogger(log_file, session_id="s")
    logger.close()
    logger.close()  # second call must not raise or write a duplicate marker

    rows = _read_jsonl(log_file)
    assert sum(1 for r in rows if r["kind"] == "session_end") == 1


def test_writes_after_close_are_silently_dropped(tmp_path):
    log_file = tmp_path / "log.jsonl"
    logger = ConversationLogger(log_file, session_id="s")
    logger.close()
    logger.log_user_message("too late")  # must not raise

    rows = _read_jsonl(log_file)
    assert not any(r.get("text") == "too late" for r in rows)


def test_default_log_path_under_dot_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Re-import default_log_path's module-level constant fresh
    import cli_textual.core.conversation_log as cl

    monkeypatch.setattr(cl, "DEFAULT_LOG_DIR", tmp_path / ".cli-textual" / "convos")
    p = cl.default_log_path("deadbeef-1234")
    assert p.parent == tmp_path / ".cli-textual" / "convos"
    assert p.parent.exists()
    assert p.suffix == ".jsonl"
    assert "deadbeef" in p.name
