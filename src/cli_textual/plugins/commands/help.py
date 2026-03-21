from typing import List
from cli_textual.core.command import SlashCommand

class HelpCommand(SlashCommand):
    """Command to display help text for all registered commands."""
    
    @property
    def name(self) -> str:
        return "/help"

    @property
    def description(self) -> str:
        return "Show this help text"

    async def execute(self, app, args: List[str]):
        help_text = app.command_manager.get_all_help()
        app.add_to_history(help_text)
