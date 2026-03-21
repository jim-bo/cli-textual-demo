import pytest
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from textual.widgets import OptionList, TextArea

@pytest.mark.asyncio
async def test_cancel_with_esc():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger /select
        text_area.text = "/select"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        app.save_screenshot("debug_tools.svg")
        container = app.query_one("#interaction-container")
        assert "visible" in container.classes
        
        # 2. Press Escape
        await pilot.press("escape")
        await pilot.pause(0.5)
        
        # 3. Verify it is hidden and focus returned
        assert "visible" not in container.classes
        assert text_area.has_focus

@pytest.mark.asyncio
async def test_auto_cancel_on_tab():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger /select
        text_area.text = "/select"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        app.save_screenshot("debug_tools.svg")
        container = app.query_one("#interaction-container")
        assert "visible" in container.classes
        
        # 2. Manually refocus the main input to trigger Blur on the OptionList
        text_area.focus()
        await pilot.pause(0.5)
        
        # 3. Verify it is hidden automatically
        assert "visible" not in container.classes
