from typing import List
from urllib.parse import urlsplit, urlunsplit

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

from cli_textual.agents.mcp import (
    get_mcp_servers,
    import_to_user_config,
    user_config_path,
)
from cli_textual.core.command import SlashCommand


# Config values are env-expanded before this runs, so a token could be sitting in
# a CLI arg or a URL. Redact before rendering into chat history.
_SECRET_HINTS = ("token", "key", "secret", "password", "passwd", "bearer", "auth")


def _redact_args(parts) -> list[str]:
    """Mask secret-looking CLI args: a ``--token``/``KEY=`` part *and* the value
    that follows a bare secret flag (e.g. ``--token sk-abc`` → ``[REDACTED]``)."""
    out: list[str] = []
    redact_next = False
    for part in parts:
        p = str(part)
        looks_secret = any(h in p.lower() for h in _SECRET_HINTS)
        if redact_next:
            out.append("[REDACTED]")
            redact_next = False
        elif looks_secret and "=" in p:
            out.append(f"{p.split('=', 1)[0]}=[REDACTED]")
        elif looks_secret:
            out.append("[REDACTED]")
            redact_next = True  # also mask the following value
        else:
            out.append(p)
    return out


def _safe_url(url: str) -> str:
    """Show scheme/host/port/path only — drop userinfo, query, and fragment,
    where credentials typically live."""
    u = urlsplit(str(url))
    host = u.hostname or ""
    if u.port:
        host = f"{host}:{u.port}"
    return urlunsplit((u.scheme, host, u.path, "", ""))


def _describe(server) -> str:
    """One-line summary of a configured MCP server: id, transport, target.

    Target strings are sanitized (secret-looking args masked, URL credentials
    stripped) so the `/mcp` listing can't leak env-expanded tokens into history.
    """
    name = getattr(server, "id", None) or "(unnamed)"
    if isinstance(server, MCPServerStdio):
        target = " ".join(_redact_args([server.command, *(server.args or [])]))
        transport = "stdio"
    elif isinstance(server, MCPServerSSE):
        target = _safe_url(server.url)
        transport = "sse"
    elif isinstance(server, MCPServerStreamableHTTP):
        target = _safe_url(server.url)
        transport = "http"
    else:  # pragma: no cover — future transports
        target = ""
        transport = type(server).__name__
    return f"- **{name}** ({transport}) → `{target}`"


class MCPCommand(SlashCommand):
    name = "/mcp"
    description = "List configured MCP servers (/mcp import claude|gemini)"

    async def execute(self, app, args: List[str]):
        if args and args[0] == "import":
            await self._import(app, args[1:])
            return
        servers = get_mcp_servers()
        if not servers:
            app.add_to_history(
                "No MCP servers configured. Add a `.mcp.json` at the workspace "
                "root (`{\"mcpServers\": {...}}`), pass `mcp_servers=` to ChatApp, "
                "or run `/mcp import claude|gemini` to pull in servers configured "
                "in another tool."
            )
            return
        lines = ["**MCP servers:**", *[_describe(s) for s in servers]]
        app.add_to_history("\n".join(lines))

    async def _import(self, app, args: List[str]):
        source = args[0] if args else ""
        if source not in ("claude", "gemini"):
            app.add_to_history("Usage: `/mcp import claude` or `/mcp import gemini`")
            return
        try:
            added, skipped = import_to_user_config(source)
        except Exception as exc:  # noqa: BLE001
            app.add_to_history(f"MCP import failed: {type(exc).__name__}: {exc}")
            return
        if not added and not skipped:
            app.add_to_history(f"No MCP servers found in your {source} config.")
            return
        msg = [f"Imported from **{source}** into `{user_config_path()}`:"]
        if added:
            msg.append(f"- added: {', '.join(added)}")
        if skipped:
            msg.append(f"- already present (kept): {', '.join(skipped)}")
        msg.append("\nRestart cli-textual to connect the new servers.")
        app.add_to_history("\n".join(msg))
