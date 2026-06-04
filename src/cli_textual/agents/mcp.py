"""MCP (Model Context Protocol) client support.

cli-textual attaches MCP servers to its pydantic-ai agent as *toolsets*. Each
configured server's tools become available to the LLM and render in the TUI
exactly like the built-in tools, because every MCP tool call is routed through
:func:`_emit_events` — a ``process_tool_call`` hook that emits the standard
``AgentToolStart`` → ``AgentToolOutput`` → ``AgentToolEnd`` lifecycle onto the
per-run event queue carried by :class:`~cli_textual.core.chat_events.ChatDeps`.

Servers are declared two ways (both supported, merged):

- a ``.mcp.json`` file at the workspace root using the de-facto-standard schema::

      {"mcpServers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
                      "remote": {"url": "https://example.com/mcp"}}}

- programmatically, via ``ChatApp(mcp_servers=[MCPServerStdio(...), ...])``.

The module keeps a process-wide list (set by the app at startup) that
``agents.manager.build_agent`` reads — mirroring ``tools/registry.py``.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.mcp import (
    MCPServer,
    MCPServerSSE,
    MCPServerStdio,
    MCPServerStreamableHTTP,
)

from cli_textual.core.chat_events import (
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
    ChatDeps,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILENAME = ".mcp.json"

# Process-wide list of configured servers, set by ``ChatApp`` at startup and
# read by ``agents.manager.build_agent``. Parallels ``tools/registry.py``.
_mcp_servers: list[MCPServer] = []


async def _emit_events(
    ctx: RunContext[ChatDeps],
    call_func: Any,
    name: str,
    tool_args: dict[str, Any],
) -> Any:
    """``process_tool_call`` hook: run an MCP tool, emitting UI lifecycle events.

    Bridges MCP tool calls into cli-textual's event protocol so they render
    identically to built-in tools. ``ctx.deps`` is the run's
    :class:`ChatDeps`, so we reach ``event_queue`` from here; the queue lookup
    is defensive (a run without ChatDeps just executes the tool silently).
    """
    queue = getattr(getattr(ctx, "deps", None), "event_queue", None)
    if queue is not None:
        await queue.put(AgentToolStart(tool_name=name, args=tool_args))
    try:
        result = await call_func(name, tool_args)
    except Exception as exc:  # noqa: BLE001 — surface any MCP failure to the UI
        if queue is not None:
            await queue.put(
                AgentToolOutput(
                    tool_name=name, content=f"{type(exc).__name__}: {exc}", is_error=True
                )
            )
            await queue.put(AgentToolEnd(tool_name=name, result="error"))
        raise
    if queue is not None:
        content = result if isinstance(result, str) else repr(result)
        await queue.put(AgentToolOutput(tool_name=name, content=content, is_error=False))
        await queue.put(AgentToolEnd(tool_name=name, result="ok"))
    return result


def _expand(value: Any) -> Any:
    """Recursively expand ``$VAR`` / ``${VAR}`` in strings so secrets (tokens,
    keys) can live in the environment instead of the committed config file."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _server_from_entry(name: str, entry: dict[str, Any]) -> MCPServer:
    """Build one ``MCPServer`` from a ``.mcp.json`` ``mcpServers`` entry.

    ``command`` → stdio transport; ``url`` → HTTP transport (Streamable HTTP by
    default, SSE when ``"type": "sse"``). The server ``id``/``tool_prefix`` are
    set to ``name`` so its tools are namespaced and identifiable in the UI.
    ``$VAR``/``${VAR}`` references in string fields are expanded from the
    environment.
    """
    entry = _expand(entry)
    common = dict(
        id=name,
        tool_prefix=name,
        process_tool_call=_emit_events,
    )
    if "command" in entry:
        return MCPServerStdio(
            command=entry["command"],
            args=list(entry.get("args", [])),
            env=entry.get("env"),
            cwd=entry.get("cwd"),
            **common,
        )
    if "url" in entry:
        cls = MCPServerSSE if entry.get("type") == "sse" else MCPServerStreamableHTTP
        return cls(url=entry["url"], headers=entry.get("headers"), **common)
    raise ValueError(
        f"MCP server {name!r}: entry must have either 'command' (stdio) or 'url' (http)"
    )


def user_config_path() -> Path:
    """cli-textual's own user-scope config: ``$XDG_CONFIG_HOME/cli-textual/mcp.json``
    (falling back to ``~/.config/cli-textual/mcp.json``)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "cli-textual" / "mcp.json"


def _read_entries(path: Path | None) -> dict[str, dict]:
    """Return the ``mcpServers`` map from a config file, or ``{}`` if missing
    or malformed (a typo must never crash startup)."""
    if path is None or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text())
        return dict(data.get("mcpServers") or {})
    except (json.JSONDecodeError, OSError, AttributeError, TypeError) as exc:
        logger.warning("MCP: could not read %s: %s", path, exc)
        return {}


# --- Opt-in import from other tools' configs (Claude Code, Gemini CLI) --------
# These tools' user/global configs are NOT read by default — only when the user
# asks (the ``discover=`` arg / ``ChatApp(mcp_discover=...)`` / ``/mcp import``),
# because silently inheriting another tool's servers is surprising and would
# undercut SAFE_MODE.

def _claude_config_paths() -> list[Path]:
    return [Path(os.path.expanduser("~/.claude.json"))]


def _gemini_config_paths() -> list[Path]:
    # Ordered low→high precedence: user, then project (project overrides user).
    return [
        Path(os.path.expanduser("~/.gemini/settings.json")),
        Path.cwd() / ".gemini" / "settings.json",
    ]


def _normalize_claude(entry: dict) -> dict:
    """Claude's ``.mcp.json``/``~/.claude.json`` entries already use our schema
    (``command``/``args``/``env``/``cwd`` or ``type``/``url``/``headers``)."""
    keys = ("command", "args", "env", "cwd", "url", "headers", "type")
    return {k: entry[k] for k in keys if k in entry}


def _normalize_gemini(entry: dict) -> dict:
    """Map a Gemini ``mcpServers`` entry onto our schema. Gemini uses ``httpUrl``
    for Streamable HTTP and ``url`` for SSE (the opposite-ish of ours)."""
    if "command" in entry:
        return {k: entry[k] for k in ("command", "args", "env", "cwd") if k in entry}
    if "httpUrl" in entry:
        out = {"url": entry["httpUrl"]}
        if "headers" in entry:
            out["headers"] = entry["headers"]
        return out
    if "url" in entry:  # Gemini's plain `url` is the SSE transport
        out = {"url": entry["url"], "type": "sse"}
        if "headers" in entry:
            out["headers"] = entry["headers"]
        return out
    return dict(entry)  # let the builder reject it


def external_entries(source: str) -> dict[str, dict]:
    """Read + normalize another tool's MCP server definitions to our schema.

    ``source`` is ``"claude"`` or ``"gemini"``. Returns ``{name: entry}``;
    missing files yield ``{}``. Raises ``ValueError`` for an unknown source.
    """
    merged: dict[str, dict] = {}
    if source == "claude":
        for path in _claude_config_paths():
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("MCP: could not read %s: %s", path, exc)
                continue
            for name, entry in (data.get("mcpServers") or {}).items():
                merged[name] = _normalize_claude(entry)
            # Claude stores local-scope servers per project under projects[<cwd>].
            project = (data.get("projects") or {}).get(str(Path.cwd()), {})
            for name, entry in (project.get("mcpServers") or {}).items():
                merged[name] = _normalize_claude(entry)
        return merged
    if source == "gemini":
        for path in _gemini_config_paths():  # low→high precedence
            for name, entry in _read_entries(path).items():
                merged[name] = _normalize_gemini(entry)
        return merged
    raise ValueError(f"unknown MCP import source {source!r} (expected 'claude' or 'gemini')")


def load_mcp_servers(
    config_path: Path | None = None,
    extra: list[MCPServer] | None = None,
    user_scope: bool = True,
    discover: list[str] | None = None,
) -> list[MCPServer]:
    """Load MCP servers from all configured scopes, by precedence.

    Sources are merged by server name, lowest → highest precedence:

    1. ``discover`` — opt-in import from other tools (``["claude", "gemini"]``).
    2. user scope — cli-textual's own :func:`user_config_path`.
    3. project scope — ``config_path`` or ``./.mcp.json``.
    4. ``extra`` — pre-constructed servers (the ``ChatApp(mcp_servers=...)`` path).

    A later source overrides an earlier one with the same name, so local/explicit
    config always wins over inherited config. Malformed files and bad individual
    entries are logged and skipped, never raised.
    """
    entries: dict[str, dict] = {}
    for source in discover or []:
        try:
            entries.update(external_entries(source))
        except ValueError as exc:
            logger.warning("MCP: %s", exc)
    if user_scope:
        entries.update(_read_entries(user_config_path()))
    entries.update(_read_entries(config_path or (Path.cwd() / DEFAULT_CONFIG_FILENAME)))

    servers: dict[str, MCPServer] = {}
    for name, entry in entries.items():
        try:
            servers[name] = _server_from_entry(name, entry)
        except Exception as exc:  # noqa: BLE001 — skip the bad entry, keep the rest
            logger.warning("MCP: skipping server %r: %s", name, exc)
    for server in extra or []:
        servers[getattr(server, "id", None) or f"_extra{len(servers)}"] = server
    return list(servers.values())


def import_to_user_config(source: str) -> tuple[list[str], list[str]]:
    """Import another tool's servers into cli-textual's user-scope config file.

    Reads + normalizes ``source`` ("claude"/"gemini") and merges new entries
    into :func:`user_config_path` (existing entries of the same name are kept,
    not overwritten). Returns ``(added_names, skipped_existing_names)``. The
    caller should restart so the new servers connect.
    """
    incoming = external_entries(source)
    path = user_config_path()
    existing = _read_entries(path)
    added, skipped = [], []
    for name, entry in incoming.items():
        if name in existing:
            skipped.append(name)
        else:
            existing[name] = entry
            added.append(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": existing}, indent=2))
    return added, skipped


def set_mcp_servers(servers: list[MCPServer]) -> None:
    """Replace the process-wide MCP server list (called by ``ChatApp``)."""
    global _mcp_servers
    _mcp_servers = list(servers)


def get_mcp_servers() -> list[MCPServer]:
    """Return the configured MCP servers (read by ``build_agent``)."""
    return list(_mcp_servers)


def reset_mcp_servers() -> None:
    """Clear the configured servers. Intended for tests."""
    global _mcp_servers
    _mcp_servers = []
