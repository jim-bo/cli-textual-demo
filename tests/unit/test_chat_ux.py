import pytest
from textual.widgets import Markdown, Static, Label
from cli_textual.app import ChatApp
from cli_textual.core.dummy_agent import DummyAgent
from cli_textual.core.chat_events import AgentThinking, AgentComplete

@pytest.mark.asyncio
async def test_chat_agent_loop():
    """Verify the full agent interaction loop: Thinking -> Tool -> Stream."""
    app = ChatApp()
    # Inject dummy agent for predictable testing
    app.agent = DummyAgent()
    
    async with app.run_test() as pilot:
        # 1. Submit a message
        await pilot.press(*"hello", "enter")
        await pilot.pause(0.2) # Wait for history update
        
        # 2. Check for user message in history
        history = app.query_one("#history-container")
        user_msgs = list(history.query(".user-msg"))
        assert any("hello" in str(msg.render()) for msg in user_msgs)
        
        # 3. Assert Thinking indicator appears
        await pilot.pause(0.1)
        assert len(app.query(".agent-spinner")) == 1
        
        # 4. Assert Tool call state
        await pilot.pause(0.6) 
        task_label = app.query_one("#task-label", Label)
        assert "list_directory" in str(task_label.render())
        
        # 5. Assert Streaming begins (Markdown widget appears)
        await pilot.pause(1.5) # Allow streaming to start and spinner to be removed
        ai_msg = app.query(".ai-msg").last(Markdown)
        assert ai_msg is not None
        assert "I've scanned" in getattr(ai_msg, "_markdown", "")
        
        # 6. Assert Completion (Spinner removed)
        await pilot.pause(2.0)
        assert len(app.query(".agent-spinner")) == 0
        assert "How can I help" in getattr(ai_msg, "_markdown", "")
