import pytest
from textual import events
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea

@pytest.mark.asyncio
async def test_paste_trigger_change():
    """Verify that pasting into the main input triggers a Changed event."""
    app = ChatApp()
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        text_area.focus()
        
        # Long text to trigger height change
        long_text = "line1\nline2\nline3"
        app.post_message(events.Paste(long_text))
        
        await pilot.pause(0.1)
        
        # Verify the text was actually pasted
        assert long_text in text_area.text
        # Verify height grew (Changed message was processed)
        assert text_area.styles.height.value >= 3
