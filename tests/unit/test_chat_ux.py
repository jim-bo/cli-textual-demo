import pytest
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage
from textual.widgets import Markdown
from cli_textual.app import ChatApp
from cli_textual.agents.orchestrators import manager_agent


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

            content = getattr(md_widget, "_markdown", "")
            assert RESPONSE_TEXT in content, \
                f"Response text missing from _markdown. Got: {repr(content)}"

            child_blocks = list(md_widget.query("*"))
            assert child_blocks, (
                "Markdown widget has no rendered child blocks. "
                "This means update() was called without await — the widget appears blank to the user."
            )
