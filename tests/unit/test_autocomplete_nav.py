import pytest
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from textual.widgets import OptionList, TextArea

@pytest.mark.asyncio
async def test_autocomplete_navigation():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger autocomplete
        await pilot.press("/")
        await pilot.pause(0.1)
        
        autocomplete = app.query_one("#autocomplete-list", OptionList)
        assert autocomplete.has_class("visible")
        
        # Initial highlight should be 0
        assert autocomplete.highlighted == 0
        
        # 2. Press down
        await pilot.press("down")
        await pilot.pause(0.1)
        
        # Highlight should move, focus should stay on input
        assert autocomplete.highlighted == 1
        assert text_area.has_focus
        
        # 3. Press up
        await pilot.press("up")
        await pilot.pause(0.1)
        assert autocomplete.highlighted == 0
        assert text_area.has_focus

@pytest.mark.asyncio
async def test_autocomplete_tab_completion():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger autocomplete with filter
        text_area.text = "/h"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.pause(0.1)
        
        autocomplete = app.query_one("#autocomplete-list", OptionList)
        assert autocomplete.has_class("visible")
        
        # 2. Press Tab to complete
        await pilot.press("tab")
        await pilot.pause(0.1)
        
        # 3. Verify text is updated and dropdown hidden
        assert text_area.text == "/head "
        assert not autocomplete.has_class("visible")
        assert text_area.has_focus
