import pytest
import time
from cli_textual.app import ChatApp

@pytest.mark.asyncio
async def test_double_ctrl_d_exit():
    app = ChatApp()
    async with app.run_test() as pilot:
        # First Ctrl+D - should trigger notification but stay running
        await pilot.press("ctrl+d")
        assert app.is_running == True
        
        # Second Ctrl+D immediately - should exit
        await pilot.press("ctrl+d")
        
        # Give it a moment to process the exit
        await pilot.pause(0.1)
        assert app.return_code is not None or app._closed_event.is_set()

@pytest.mark.asyncio
async def test_single_ctrl_d_timeout():
    app = ChatApp()
    async with app.run_test() as pilot:
        # First Ctrl+D
        await pilot.press("ctrl+d")
        assert app.is_running == True
        
        # Wait for timeout (1.1s > 1.0s)
        await pilot.pause(1.1)
        
        # Second Ctrl+D after timeout - should still be running because it's treated as a "new" first press
        await pilot.press("ctrl+d")
        assert app.is_running == True
