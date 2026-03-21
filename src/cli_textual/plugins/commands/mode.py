from typing import List
from cli_textual.core.command import SlashCommand

class ModeCommand(SlashCommand):
    """Command to toggle the agent orchestration mode."""
    
    @property
    def name(self) -> str:
        return "/mode"

    @property
    def description(self) -> str:
        return "Set chat mode (dummy, procedural, manager)"

    async def execute(self, app, args: List[str]):
        if args and args[0] in ["dummy", "procedural", "manager"]:
            app.chat_mode = args[0]
            app.add_to_history(f"Chat mode set to: **{app.chat_mode}**")
            app.query_one(".mode-info").update(f"mode: {app.chat_mode}")
        else:
            app.add_to_history("Usage: `/mode <dummy|procedural|manager>`")
