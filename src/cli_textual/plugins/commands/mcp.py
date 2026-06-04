from typing import List

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

from cli_textual.agents.mcp import get_mcp_servers
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
    description = "List configured MCP servers"

    async def execute(self, app, args: List[str]):
        servers = get_mcp_servers()
        if not servers:
            app.add_to_history(
                "No MCP servers configured. Add a `.mcp.json` at the workspace "
                "root (`{\"mcpServers\": {...}}`) or pass `mcp_servers=` to ChatApp."
            )
            return
        lines = ["**MCP servers:**", *[_describe(s) for s in servers]]
        app.add_to_history("\n".join(lines))
