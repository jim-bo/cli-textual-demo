import pytest
from cli_textual.app import ChatApp
from textual.widgets import OptionList, Label

@pytest.mark.asyncio
async def test_mode_command_no_args_triggers_ui():
    """Verify that /mode without args opens the selection UI without crashing."""
    app = ChatApp()
    async with app.run_test() as pilot:
        # Type the command
        for char in "/mode":
            await pilot.press(char)
        await pilot.press("enter")
        
        # We expect the interaction container to have a Label and an OptionList
        interaction = app.query_one("#interaction-container")
        assert interaction.has_class("visible")
        
        # This is where the NameError would happen during the pilot.press("enter")
        # If we reach here, we check for the elements
        assert interaction.query_one(Label)
        assert interaction.query_one(OptionList)
        assert interaction.query_one("#mode-select-list")
