from typing import List

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

from cli_textual.agents.mcp import (
    get_mcp_servers,
    import_to_user_config,
    user_config_path,
)
from cli_textual.core.command import SlashCommand


def _describe(server) -> str:
    """One-line summary of a configured MCP server: id, transport, target."""
    name = getattr(server, "id", None) or "(unnamed)"
    if isinstance(server, MCPServerStdio):
        target = " ".join([server.command, *server.args])
        transport = "stdio"
    elif isinstance(server, MCPServerSSE):
        target = server.url
        transport = "sse"
    elif isinstance(server, MCPServerStreamableHTTP):
        target = server.url
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
