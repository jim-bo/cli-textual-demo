"""Tests for thinking/reasoning transparency layer."""
import asyncio
import pytest
from pydantic_ai.models.function import FunctionModel, AgentInfo, DeltaThinkingPart
from pydantic_ai.messages import ModelMessage
from textual.widgets import Collapsible

from cli_textual.agents.manager import run_manager_pipeline, manager_agent
from cli_textual.core.chat_events import (
    AgentThinkingChunk, AgentThinkingComplete, AgentStreamChunk, AgentComplete,
)
from cli_textual.app import ChatApp


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_emits_thinking_chunks():
    """Thinking tokens surface as AgentThinkingChunk events."""
    async def thinking_then_text(messages: list[ModelMessage], info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Let me reason about this.")}
        yield "Here is my answer."

    input_queue = asyncio.Queue()
    events = []
    with manager_agent.override(model=FunctionModel(stream_function=thinking_then_text)):
        async with asyncio.timeout(5):
            async for event in run_manager_pipeline("test", input_queue):
                events.append(event)

    thinking_chunks = [e for e in events if isinstance(e, AgentThinkingChunk)]
    assert thinking_chunks, "No AgentThinkingChunk events emitted"

    thinking_complete = [e for e in events if isinstance(e, AgentThinkingComplete)]
    assert thinking_complete, "No AgentThinkingComplete event emitted"
    assert "reason" in thinking_complete[0].full_text.lower()

    text_chunks = [e for e in events if isinstance(e, AgentStreamChunk)]
    assert text_chunks, "No text chunks emitted"
    assert isinstance(events[-1], AgentComplete)


@pytest.mark.asyncio
async def test_pipeline_no_thinking_still_works():
    """Existing behavior preserved when model produces no thinking."""
    async def text_only(messages: list[ModelMessage], info: AgentInfo):
        yield "Just text, no thinking."

    input_queue = asyncio.Queue()
    events = []
    with manager_agent.override(model=FunctionModel(stream_function=text_only)):
        async with asyncio.timeout(5):
            async for event in run_manager_pipeline("test", input_queue):
                events.append(event)

    thinking_chunks = [e for e in events if isinstance(e, AgentThinkingChunk)]
    assert not thinking_chunks, "Unexpected thinking chunks for text-only model"
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)


# ---------------------------------------------------------------------------
# TUI tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_thinking_renders_collapsed_by_default():
    """Thinking appears in a collapsed Collapsible widget."""
    async def thinking_then_text(messages: list[ModelMessage], info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Deep thought here")}
        yield "Final answer."

    app = ChatApp()
    with manager_agent.override(model=FunctionModel(stream_function=thinking_then_text)):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"hello", "enter")
            await pilot.pause(2.0)

            collapsibles = list(app.query_one("#history-container").query("Collapsible.thinking-block"))
            assert collapsibles, "No Collapsible widget found for thinking"
            assert collapsibles[0].collapsed is True


@pytest.mark.asyncio
async def test_verbose_mode_expands_thinking():
    """With verbose_mode=True, thinking is expanded."""
    async def thinking_then_text(messages: list[ModelMessage], info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Deep thought here")}
        yield "Final answer."

    app = ChatApp()
    app.verbose_mode = True
    with manager_agent.override(model=FunctionModel(stream_function=thinking_then_text)):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"hello", "enter")
            await pilot.pause(2.0)

            collapsibles = list(app.query_one("#history-container").query("Collapsible.thinking-block"))
            assert collapsibles, "No Collapsible widget found"
            assert collapsibles[0].collapsed is False


@pytest.mark.asyncio
async def test_verbose_command_toggles():
    """/verbose toggles app.verbose_mode."""
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.verbose_mode is False
        await pilot.press(*"/verbose", "enter")
        await pilot.pause(0.5)
        assert app.verbose_mode is True
