from typing import List
from cli_textual.core.command import SlashCommand

class ClearCommand(SlashCommand):
    name = "/clear"
    description = "Clear history"

    async def execute(self, app, args: List[str]):
        app.query_one("#history-container").query("*").remove()
        app.message_history = []
        app.notify("Chat memory cleared.")
