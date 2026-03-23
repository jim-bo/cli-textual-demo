import json
import asyncio
import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel, AgentInfo, DeltaToolCall
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart

from cli_textual.agents.orchestrators import manager_agent, run_manager_pipeline
from cli_textual.core.chat_events import AgentRequiresUserInput, AgentStreamChunk, AgentComplete, AgentThinking


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect_pipeline(pipeline, input_queue, auto_respond=None):
    """Drain a pipeline, optionally responding to any AgentRequiresUserInput."""
    events = []
    async for event in pipeline:
        events.append(event)
        if isinstance(event, AgentRequiresUserInput) and auto_respond is not None:
            await input_queue.put(auto_respond)
    return events


def _has_tool_return(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(msg, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in msg.parts)
        for msg in messages
    )


# ---------------------------------------------------------------------------
# Stream functions for FunctionModel
# ---------------------------------------------------------------------------

async def text_only_stream(messages: list[ModelMessage], agent_info: AgentInfo):
    """Simulates an LLM that ignores the tool and just writes text."""
    yield "Once upon a time, there was a red sunset that painted the sky crimson."


async def select_then_text_stream(messages: list[ModelMessage], agent_info: AgentInfo):
    """Simulates an LLM that correctly calls ask_user_to_select first, then responds."""
    if _has_tool_return(messages):
        # Second call after the tool returned: write the story
        yield "Here is your story about the chosen color!"
    else:
        # First call: issue the tool call
        yield {
            0: DeltaToolCall(
                name="ask_user_to_select",
                json_args=json.dumps({
                    "prompt": "Choose a primary color:",
                    "options": ["Red", "Blue", "Yellow"],
                }),
            )
        }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_plumbing_with_forced_tool_call():
    """Verify the pipeline infrastructure works when the tool IS called.

    Uses TestModel(call_tools=[...]) to force tool invocation — this tests
    the event-queue / input-queue bridge, not LLM prompt quality.
    """
    input_queue = asyncio.Queue()
    mock_model = TestModel(call_tools=["ask_user_to_select"])

    with manager_agent.override(model=mock_model):
        pipeline = run_manager_pipeline(
            "Tell me a story about a primary color but first let me select a color",
            input_queue,
        )
        events = await _collect_pipeline(pipeline, input_queue, auto_respond="Blue")

    assert any(isinstance(e, AgentRequiresUserInput) for e in events)
    req = next(e for e in events if isinstance(e, AgentRequiresUserInput))
    assert req.tool_name == "/select"
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)


@pytest.mark.asyncio
async def test_pipeline_text_only_emits_no_user_input_event():
    """Document what happens when the LLM returns text without calling the tool.

    This test captures the BROKEN behavior: if the LLM ignores ask_user_to_select,
    no AgentRequiresUserInput event is emitted and the user never gets a choice.
    A passing test here means the pipeline handles this gracefully (no crash),
    but the user experience is wrong — the LLM should always call the tool.
    """
    input_queue = asyncio.Queue()
    text_only_model = FunctionModel(stream_function=text_only_stream)

    with manager_agent.override(model=text_only_model):
        pipeline = run_manager_pipeline(
            "Tell me a story about a primary color but first let me select a color",
            input_queue,
        )
        events = await _collect_pipeline(pipeline, input_queue)

    # No selection event — the LLM skipped the tool
    assert not any(isinstance(e, AgentRequiresUserInput) for e in events)
    # But we still get text and a clean completion
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)


@pytest.mark.asyncio
async def test_pipeline_with_function_model_select_then_respond():
    """Verify the full selection flow using a FunctionModel that mimics correct LLM behavior.

    This tests the same pipeline path a real LLM takes when it respects the
    system prompt and calls ask_user_to_select before writing a response.
    """
    input_queue = asyncio.Queue()
    select_model = FunctionModel(stream_function=select_then_text_stream)

    with manager_agent.override(model=select_model):
        pipeline = run_manager_pipeline(
            "Tell me a story about a primary color but first let me select a color",
            input_queue,
        )
        events = await _collect_pipeline(pipeline, input_queue, auto_respond="Red")

    # Must get a selection event
    assert any(isinstance(e, AgentRequiresUserInput) for e in events), \
        "Expected AgentRequiresUserInput but LLM skipped the tool"

    req = next(e for e in events if isinstance(e, AgentRequiresUserInput))
    assert req.tool_name == "/select"
    assert len(req.options) > 0

    # Must get a text response after the selection
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)
