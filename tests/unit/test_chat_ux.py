import pytest
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage
from textual.widgets import Markdown, Static, Label
from cli_textual.app import ChatApp
from cli_textual.core.dummy_agent import DummyAgent
from cli_textual.core.chat_events import AgentThinking, AgentComplete
from cli_textual.agents.orchestrators import manager_agent

@pytest.mark.asyncio
async def test_chat_agent_loop():
    """Verify the full agent interaction loop: Thinking -> Tool -> Stream."""
    app = ChatApp()
    app.chat_mode = "dummy"
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


@pytest.mark.asyncio
async def test_manager_response_renders_in_tui():
    """Verify that the manager pipeline response actually appears rendered in the UI.

    This test specifically guards against the Markdown.update() await bug:
    - Markdown._markdown (set synchronously) would be non-empty even without await
    - But Markdown's child MarkdownBlock widgets are only created in the async part
    - Without `await markdown_widget.update(...)`, children are never mounted
      and the widget renders as a blank Blank object despite _markdown being set.
    """
    RESPONSE_TEXT = "Sentinel response from the deterministic test model."

    async def fixed_response(messages: list[ModelMessage], agent_info: AgentInfo):
        yield RESPONSE_TEXT

    app = ChatApp()
    app.chat_mode = "manager"

    with manager_agent.override(model=FunctionModel(stream_function=fixed_response)):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"hello", "enter")
            await pilot.pause(2.0)

            history = app.query_one("#history-container")
            ai_widgets = list(history.query(".ai-msg"))
            assert ai_widgets, "No .ai-msg widget found — response was never rendered"

            md_widget = ai_widgets[-1]
            assert isinstance(md_widget, Markdown), \
                f"Expected Markdown widget, got {type(md_widget).__name__}"

            # _markdown is set synchronously — this alone does NOT prove rendering worked
            content = getattr(md_widget, "_markdown", "")
            assert RESPONSE_TEXT in content, \
                f"Response text missing from _markdown. Got: {repr(content)}"

            # MarkdownBlock children are only created by the async part of update().
            # If update() was not awaited, this list will be empty and the widget
            # displays as blank despite _markdown being set.
            child_blocks = list(md_widget.query("*"))
            assert child_blocks, (
                "Markdown widget has no rendered child blocks. "
                "This means update() was called without await — the widget appears blank to the user."
            )
