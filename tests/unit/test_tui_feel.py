"""TUI tests for the Tier-1 feat/tui-feel slice: tool-call args display,
esc-to-interrupt, and the token/cost/context status bar."""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from cli_textual.app import ChatApp
from cli_textual.agents.manager import manager_agent
from textual.widgets import Collapsible, Label, Static


# ---------------------------------------------------------------------------
# Tool-call args display
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_call_renders_args_in_title_and_body(tmp_path):
    """A tool call should render ``name(args)`` in the collapsible title and a
    full args JSON block in the expandable body."""
    target = tmp_path / "hello.txt"
    target.write_text("file contents here")

    async def stream_fn(messages, info):
        returned = any(
            isinstance(p, ToolReturnPart)
            for m in messages
            for p in getattr(m, "parts", [])
        )
        if not returned:
            yield {0: DeltaToolCall(
                name="read_file",
                json_args=json.dumps({"path": str(target)}),
            )}
        else:
            yield "done"

    app = ChatApp()
    app.chat_mode = "manager"

    with manager_agent.override(model=FunctionModel(stream_function=stream_fn)):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"read it", "enter")
            await pilot.pause(2.0)

            history = app.query_one("#history-container")
            colls = list(history.query(Collapsible))
            tool_rows = [c for c in colls if "tool-output-block" in c.classes]
            assert tool_rows, "No tool-output Collapsible was rendered"

            title = tool_rows[-1].title
            assert "read_file(" in title, f"args not in title: {title!r}"
            assert "path=" in title, f"args not in title: {title!r}"

            args_blocks = list(tool_rows[-1].query(".tool-args"))
            assert args_blocks, "No .tool-args JSON block in the expanded body"
            assert "path" in str(args_blocks[0].render())


# ---------------------------------------------------------------------------
# Esc-to-interrupt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escape_interrupts_running_stream():
    """Pressing Esc mid-stream cancels the worker and shows a Stopped affordance,
    without further chunks rendering."""
    release = asyncio.Event()

    async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
        yield "partial answer "
        # Block until the test releases us; Esc should cancel before this.
        await release.wait()
        yield "SHOULD_NOT_APPEAR"

    app = ChatApp()
    app.chat_mode = "manager"

    try:
        with manager_agent.override(model=FunctionModel(stream_function=stream_fn)):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press(*"go", "enter")
                await pilot.pause(0.3)  # let the first chunk stream in

                await pilot.press("escape")
                await pilot.pause(0.3)

                worker = app._agent_worker
                assert worker is None or not worker.is_running, "worker still running after Esc"

                history = app.query_one("#history-container")
                text = " ".join(
                    str(getattr(w, "_markdown", "")) + str(getattr(w, "renderable", ""))
                    for w in history.query("*")
                )
                assert "Stopped" in text, "No Stopped affordance rendered"
                assert "SHOULD_NOT_APPEAR" not in text, "stream kept going after Esc"
    finally:
        release.set()  # always unblock the mock stream, even if an assert fails


@pytest.mark.asyncio
async def test_second_submit_is_refused_while_streaming():
    """A new prompt submitted mid-stream is refused (not run as a 2nd worker),
    and the user's text is preserved in the input for resubmission."""
    release = asyncio.Event()

    async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
        yield "streaming… "
        await release.wait()
        yield "tail"

    app = ChatApp()
    app.chat_mode = "manager"

    try:
        with manager_agent.override(model=FunctionModel(stream_function=stream_fn)):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press(*"first", "enter")
                await pilot.pause(0.3)
                first_worker = app._agent_worker
                assert first_worker is not None and first_worker.is_running

                # Second submit while the first is still streaming.
                await pilot.press(*"second", "enter")
                await pilot.pause(0.2)

                # Same worker handle — no new stream was started.
                assert app._agent_worker is first_worker
                # The refused text is restored to the input.
                from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
                assert app.query_one("#main-input", GrowingTextArea).text == "second"
    finally:
        release.set()


# ---------------------------------------------------------------------------
# Token / cost / context status bar
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_bar_shows_usage_after_turn():
    """After a completed turn the status bar surfaces tokens / cost / context."""

    async def fixed_response(messages: list[ModelMessage], info: AgentInfo):
        yield "an answer with several tokens in it"

    app = ChatApp()
    app.chat_mode = "manager"

    with manager_agent.override(model=FunctionModel(stream_function=fixed_response)):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"hello", "enter")
            await pilot.pause(2.0)

            tok_text = str(app.query_one(".tokens-info", Label).render())
            ctx_text = str(app.query_one(".context-info", Label).render())
            cost_text = str(app.query_one(".cost-info", Label).render())
            assert "tok" in tok_text and any(ch.isdigit() for ch in tok_text)
            assert "ctx" in ctx_text and "%" in ctx_text
            assert "$" in cost_text
