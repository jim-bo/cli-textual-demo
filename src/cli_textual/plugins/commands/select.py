import time
from typing import List
from textual.containers import Horizontal
from textual.widgets import Label, OptionList
from cli_textual.core.command import SlashCommand

class SelectCommand(SlashCommand):
    name = "/select"
    description = "Show model selection"
    requires_permission = True

    async def execute(self, app, args: List[str]):
        container = app.query_one("#interaction-container")
        container.add_class("visible")
        container.query("*").remove()
        
        unique_id = f"sel-{int(time.time()*1000)}"
        option_list = OptionList("gpt-4o", "claude-3.5", id=unique_id)
        
        container.mount(Horizontal(Label("Select model:"), Label("(Esc to cancel)", classes="cancel-note")))
        container.mount(option_list)
        app.call_after_refresh(option_list.focus)
