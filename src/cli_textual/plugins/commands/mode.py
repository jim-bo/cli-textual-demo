from typing import List
from textual.widgets import Label, OptionList
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
        modes = ["dummy", "procedural", "manager"]
        
        if args and args[0] in modes:
            app.chat_mode = args[0]
            app.add_to_history(f"Chat mode set to: **{app.chat_mode}**")
            app.query_one(".mode-info").update(f"mode: {app.chat_mode}")
        else:
            # Show selection UI
            interaction = app.query_one("#interaction-container")
            interaction.add_class("visible")
            interaction.query("*").remove()
            
            interaction.mount(Label("Select Chat Orchestration Mode:"))
            options = OptionList(*modes, id="mode-select-list")
            interaction.mount(options)
            app.call_after_refresh(options.focus)
