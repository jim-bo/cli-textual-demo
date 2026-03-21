import pytest
import os
import json
from pathlib import Path
from cli_textual.app import ChatApp
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from textual.widgets import DirectoryTree, Label, DataTable

@pytest.mark.asyncio
async def test_tool_path_jailing():
    app = ChatApp()
    # Mock settings to auto-approve /ls
    os.makedirs(".cbio", exist_ok=True)
    with open(".cbio/settings.json", "w") as f:
        json.dump({"approved_tools": ["/ls"]}, f)
        
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        # Try to access a file outside the workspace
        text_area.text = "/ls ../"
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Should show a security error in history
        history = app.query_one("#history-container")
        # Search for the error in all static/markdown messages in history
        messages = [str(m.render()) for m in history.query("*")]
        assert any("Access denied" in msg for msg in messages)

@pytest.mark.asyncio
async def test_ls_mounts_tree():
    # Mock settings to auto-approve /ls for this test
    os.makedirs(".cbio", exist_ok=True)
    with open(".cbio/settings.json", "w") as f:
        json.dump({"approved_tools": ["/ls"]}, f)
    app = ChatApp()
        
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)

        text_area.text = "/ls"
        await pilot.press("enter")
        await pilot.pause(2.0)

        app.save_screenshot("ls_debug.svg")
        container = app.query_one("#interaction-container")
        assert container.query_one(DataTable)
        assert "visible" in container.classes

        # 3. Verify scrollability
        table = container.query_one(DataTable)
        assert table.allow_vertical_scroll
@pytest.mark.asyncio
async def test_permission_modal_appears():
    app = ChatApp()
    # Ensure settings is empty
    os.makedirs(".cbio", exist_ok=True)
    if os.path.exists(".cbio/settings.json"):
        os.remove(".cbio/settings.json")
        
    async with app.run_test() as pilot:
        text_area = app.query_one("#main-input", GrowingTextArea)
        
        text_area.text = "/head app.py"
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Verify a ModalScreen is pushed (we check by looking for its elements or app.screen)
        # In Textual, we can check the screen stack
        assert "PermissionScreen" in str(app.screen)
        assert "Authorize" in str(app.screen.query_one(Label).render())
