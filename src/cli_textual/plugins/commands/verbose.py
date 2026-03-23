from typing import List
from cli_textual.core.command import SlashCommand


class VerboseCommand(SlashCommand):
    """Toggle verbose mode to show agent thinking by default."""

    @property
    def name(self) -> str:
        return "/verbose"

    @property
    def description(self) -> str:
        return "Toggle verbose mode (show thinking expanded)"

    async def execute(self, app, args: List[str]):
        app.verbose_mode = not app.verbose_mode
        state = "ON" if app.verbose_mode else "OFF"
        app.add_to_history(f"Verbose mode: **{state}**")
