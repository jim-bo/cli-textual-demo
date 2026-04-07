"""Append-only JSONL conversation logger.

Captures the full debug-relevant history of a ChatApp session: user messages,
slash commands, every event the agent emits (thinking, tool start/output/end,
stream chunks, completion), and turn boundaries. One JSON object per line so
the file is greppable, tail-friendly, and replayable.

Files are written to ``~/.cli-textual/convos/<timestamp>-<sid>.jsonl`` by
default. Pass an explicit path to ``ConversationLogger`` to override.

This module has zero TUI dependencies — it can be used from tests or other
front-ends without importing Textual.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli_textual.core.chat_events import ChatEvent

DEFAULT_LOG_DIR = Path.home() / ".cli-textual" / "convos"


def default_log_path(session_id: str) -> Path:
    """Return ``~/.cli-textual/convos/<utc-timestamp>-<sid8>.jsonl``."""
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_LOG_DIR / f"{ts}-{session_id[:8]}.jsonl"


def _safe_serialize(value: Any) -> Any:
    """Best-effort JSON-friendly conversion for arbitrary payload values."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if is_dataclass(value):
            try:
                return asdict(value)
            except Exception:
                pass
        if isinstance(value, (list, tuple)):
            return [_safe_serialize(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _safe_serialize(v) for k, v in value.items()}
        return repr(value)


class ConversationLogger:
    """Append-only JSONL writer for a single ChatApp session.

    Each line is a JSON object with at least ``ts``, ``session_id``, and
    ``kind``. Higher-level methods (``log_user_message``, ``log_event``)
    add a structured payload describing the entry.

    Attributes:
        path: The file path being written to.
        session_id: The session_id passed at construction time.
    """

    def __init__(self, path: Path, session_id: str) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Line-buffered so tail -f shows entries as they happen.
        self._fh = self.path.open("a", encoding="utf-8", buffering=1)
        self._closed = False
        self._write({"kind": "session_start"})

    # ── low-level ──────────────────────────────────────────────────────────

    def _write(self, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            **{k: _safe_serialize(v) for k, v in payload.items()},
        }
        try:
            self._fh.write(json.dumps(record) + "\n")
        except Exception:
            # Logging must never break the chat loop.
            pass

    # ── high-level ─────────────────────────────────────────────────────────

    def log_user_message(self, text: str) -> None:
        """Record a free-text user message."""
        self._write({"kind": "user_message", "text": text})

    def log_user_command(self, name: str, args: list[str]) -> None:
        """Record a slash-command invocation."""
        self._write({"kind": "user_command", "name": name, "args": list(args)})

    def log_event(self, event: ChatEvent) -> None:
        """Record any ChatEvent emitted by the agent stream."""
        kind = type(event).__name__
        try:
            payload = asdict(event) if is_dataclass(event) else {}
        except Exception:
            payload = {"repr": repr(event)}
        # ``new_history`` on AgentComplete contains pydantic-ai ModelMessage
        # objects whose dataclass conversion can be lossy or huge — keep them
        # but coerce each to a string so the file stays JSON-clean.
        if "new_history" in payload and payload["new_history"]:
            payload["new_history"] = [repr(m) for m in payload["new_history"]]
        self._write({"kind": f"event:{kind}", **payload})

    def close(self) -> None:
        """Write a session_end marker and close the file handle."""
        if self._closed:
            return
        self._write({"kind": "session_end"})
        self._closed = True
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "ConversationLogger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
