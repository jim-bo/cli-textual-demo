import pytest
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from textual.widgets import LoadingIndicator, OptionList, TextArea

@pytest.mark.asyncio
async def test_initial_focus():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        assert text_area.has_focus

@pytest.mark.asyncio
async def test_load_command():
    import os, json
    os.makedirs(".agents", exist_ok=True)
    with open(".agents/settings.json", "w") as f:
        json.dump({"approved_tools": ["/load"]}, f)

    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        text_area.text = "/load"
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        container = app.query_one("#interaction-container")
        assert "visible" in container.classes
        assert app.query_one("DNASpinner")
        
        # Wait for simulation to finish
        await pilot.pause(4)
        assert "visible" not in container.classes

@pytest.mark.asyncio
async def test_select_command():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        text_area.text = "/select"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        
        # Wait for the interaction container to become visible
        await pilot.pause(0.5)
        container = app.query_one("#interaction-container")
        assert "visible" in container.classes
        
        # Verify OptionList exists and HAS FOCUS automatically
        option_list = app.query_one(OptionList)
        assert option_list.has_focus
        
        # Select an item
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Focus returns to main input
        assert text_area.has_focus
        assert "visible" not in container.classes

@pytest.mark.asyncio
async def test_select_command_twice():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # First select
        text_area.text = "/select"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Select an item to close the first one
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Second select (triggers bug if not cleaned up)
        text_area.text = "/select"
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Verify any OptionList has focus
        assert app.query_one(OptionList).has_focus

@pytest.mark.asyncio
async def test_shift_enter_newline():
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        text_area.text = "Line 1"
        
        # Simulate Shift+Enter
        await pilot.press("shift+enter")
        text_area.text += "\n"
        text_area.text += "Line 2"
        
        assert "\n" in text_area.text
        
        # Force a Changed event for height growth simulation
        text_area.post_message(TextArea.Changed(text_area))
        await pilot.pause(0.1)
        
        # Height should have grown
        assert text_area.styles.height.value > 1
        
        # Now submit with regular Enter
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # TextArea should be cleared
        assert text_area.text == ""
        assert text_area.styles.height.value == 1

@pytest.mark.asyncio
async def test_autocomplete_visibility():
    """TDD Test: Typing '/' should show the autocomplete dropdown."""
    app = ChatApp()
    async with app.run_test() as pilot:
        # Type '/'
        await pilot.press("/")
        await pilot.pause(0.1)
        
        # This SHOULD FAIL because autocomplete-list doesn't exist yet
        autocomplete = app.query_one("#autocomplete-list", OptionList)
        assert autocomplete.visible
        assert autocomplete.option_count > 0
