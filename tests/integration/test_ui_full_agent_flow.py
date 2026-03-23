import pytest
import asyncio
from textual.widgets import OptionList, Markdown, Label
from pydantic_ai.models.test import TestModel

from cli_textual.app import ChatApp
from cli_textual.agents.orchestrators import manager_agent

@pytest.mark.asyncio
async def test_full_ui_interaction_round_trip():
    """
    Verify the full loop:
    1. User sends message
    2. Agent triggers selection UI
    3. User makes selection
    4. Agent completes with final output
    """
    app = ChatApp()
    app.chat_mode = "manager"
    
    # We force the TestModel to call the selection tool
    mock_model = TestModel(call_tools=['ask_user_to_select'])
    
    async with app.run_test() as pilot:
        with manager_agent.override(model=mock_model):
            # 1. Type message and submit
            await pilot.press(*"tell me a story about a color", "enter")
            
            # 2. Wait for the interaction container to become visible
            # We use a loop to poll since agent responses are async
            for _ in range(20):
                interaction = app.query_one("#interaction-container")
                if interaction.has_class("visible") and app.query("OptionList#agent-select-tool"):
                    break
                await pilot.pause(0.1)
            else:
                pytest.fail("Interaction UI never appeared")

            # 3. Verify the selection list has options
            option_list = app.query_one("#agent-select-tool", OptionList)
            assert option_list.option_count > 0
            
            # 4. Select the first option (Red) and press enter
            await pilot.press("enter")
            
            # 5. Wait for the agent to finish and the interaction UI to close
            for _ in range(20):
                if not interaction.has_class("visible"):
                    break
                await pilot.pause(0.1)
            else:
                pytest.fail("Interaction UI never closed after selection")

            # 6. Verify the final AI message was mounted in history
            history = app.query_one("#history-container")
            # The TestModel response usually contains the tool call result or mock text
            assert len(history.query(Markdown)) >= 1
            
            # Final check that focus returned to main input
            assert app.focused.id == "main-input"
