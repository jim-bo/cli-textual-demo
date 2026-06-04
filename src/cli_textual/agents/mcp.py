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


def load_mcp_servers(
    config_path: Path | None = None,
    extra: list[MCPServer] | None = None,
) -> list[MCPServer]:
    """Load MCP servers from a ``.mcp.json`` file and/or a programmatic list.

    Args:
        config_path: Path to the JSON config. When ``None``, looks for
            ``.mcp.json`` in the current working directory. A missing file is
            not an error (returns only ``extra``).
        extra: Pre-constructed ``MCPServer`` objects to append (the
            ``ChatApp(mcp_servers=...)`` path).

    Returns:
        The combined list of servers. A malformed file or a bad individual
        entry is logged and skipped rather than raised, so a typo in config
        can never crash startup.
    """
    servers: list[MCPServer] = []
    path = config_path or (Path.cwd() / DEFAULT_CONFIG_FILENAME)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            entries = data.get("mcpServers", {})
        except (json.JSONDecodeError, OSError, AttributeError) as exc:
            logger.warning("MCP: could not read %s: %s", path, exc)
            entries = {}
        for name, entry in entries.items():
            try:
                servers.append(_server_from_entry(name, entry))
            except Exception as exc:  # noqa: BLE001 — skip the bad entry, keep the rest
                logger.warning("MCP: skipping server %r: %s", name, exc)
    if extra:
        servers.extend(extra)
    return servers


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
