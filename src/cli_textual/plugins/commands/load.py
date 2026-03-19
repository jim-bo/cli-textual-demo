import asyncio
from typing import List
from textual.containers import Horizontal
from textual.widgets import Label
from cli_textual.core.command import SlashCommand
from cli_textual.ui.widgets.dna_spinner import DNASpinner

class LoadCommand(SlashCommand):
    name = "/load"
    description = "Simulate a task"
    requires_permission = True

    async def execute(self, app, args: List[str]):
        print("DEBUG: Executing LoadCommand")
        container = app.query_one("#interaction-container")
        container.add_class("visible")
        print(f"DEBUG: Classes after add_class: {container.classes}")
        container.query("*").remove()
        container.mount(Horizontal(DNASpinner(), Label("Processing...", id="task-label"), id="task-area"))
        
        await asyncio.sleep(3)
        
        container.remove_class("visible")
        print(f"DEBUG: Classes after remove_class: {container.classes}")
        app.add_to_history("Task completed.")
        app.query_one("#main-input").focus()
