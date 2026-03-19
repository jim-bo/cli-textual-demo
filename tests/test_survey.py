import pytest
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from textual.widgets import TabbedContent, OptionList, TextArea

@pytest.mark.asyncio
async def test_survey_tabs_flow():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger /survey
        text_area.text = "/survey"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # 2. Verify TabbedContent is visible
        tabs = app.query_one(TabbedContent)
        assert tabs.visible
        assert tabs.active == "q1" # First tab should be active
        
        # 3. Answer Q1
        await pilot.press("enter") # Select first option in Q1
        await pilot.pause(0.5)
        
        # 4. Verify it moved to Q2
        assert tabs.active == "q2"
        
        # 5. Test Tab navigation back to Q1
        await pilot.press("tab")
        assert tabs.active == "q1"
        
        # 6. Test Tab navigation back to Q2
        await pilot.press("tab")
        assert tabs.active == "q2"

        # 7. Answer Q2 (Final)
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # 6. Verify interaction is cleared and focus returned
        container = app.query_one("#interaction-container")
        assert "visible" not in container.classes
        assert text_area.has_focus

@pytest.mark.asyncio
async def test_survey_manual_navigation():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # 1. Trigger /survey
        text_area.text = "/survey"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        tabs = app.query_one(TabbedContent)
        assert tabs.active == "q1"
        
        # 2. Press Ctrl+N to move to next tab
        await pilot.press("ctrl+n")
        await pilot.pause(0.1)
        assert tabs.active == "q2"
        
        # 3. Press Ctrl+P to move back to previous tab
        await pilot.press("ctrl+p")
        await pilot.pause(0.1)
        assert tabs.active == "q1"
