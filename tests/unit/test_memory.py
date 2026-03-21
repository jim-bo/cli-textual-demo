import pytest
from cli_textual.app import ChatApp
from cli_textual.core.chat_events import AgentComplete, AgentStreamChunk, AgentThinking
from pydantic_ai.messages import ModelResponse, TextPart

@pytest.mark.asyncio
async def test_memory_updates_on_complete():
    """Verify that message_history is updated when AgentComplete is received."""
    app = ChatApp()
    
    async with app.run_test() as pilot:
        # Simulate an agent yielding a complete event with new history
        mock_history = [ModelResponse(parts=[TextPart(content="Hello")])]
        
        async def mock_generator():
            yield AgentThinking(message="Starting")
            yield AgentComplete(new_history=mock_history)
            
        # We manually run the worker inside the app context
        app.run_worker(app.stream_agent_response(mock_generator()))
        
        # Wait for worker to finish
        await pilot.pause(0.1)
        
        assert len(app.message_history) == 1
        assert app.message_history[0].parts[0].content == "Hello"

@pytest.mark.asyncio
async def test_clear_command_wipes_memory():
    """Verify that /clear command resets the message_history."""
    app = ChatApp()
    app.message_history = ["some", "history"]
    
    async with app.run_test() as pilot:
        await pilot.press(*"/clear")
        await pilot.press("enter")
        
        assert app.message_history == []
