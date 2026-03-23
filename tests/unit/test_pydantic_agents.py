import asyncio
import pytest
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage
from cli_textual.agents.manager import run_manager_pipeline, manager_agent
from cli_textual.core.chat_events import (
    AgentThinking, AgentStreamChunk, AgentComplete,
)

@pytest.mark.asyncio
async def test_manager_pipeline_flow():
    """Verify that the manager pipeline initializes and completes."""
    async def fixed_response(messages: list[ModelMessage], agent_info: AgentInfo):
        yield "done"

    events = []
    input_queue = asyncio.Queue()

    with manager_agent.override(model=FunctionModel(stream_function=fixed_response)):
        async with asyncio.timeout(5):
            pipeline = run_manager_pipeline("test prompt", input_queue)
            async for event in pipeline:
                events.append(event)

    assert any(isinstance(e, AgentThinking) for e in events)
    assert isinstance(events[-1], AgentComplete)


@pytest.mark.asyncio
async def test_multi_turn_conversation_preserves_history():
    """Verify message_history flows through to subsequent pipeline runs."""
    seen_histories = []

    async def inspect_history(messages: list[ModelMessage], agent_info: AgentInfo):
        seen_histories.append(len(messages))
        yield "response"

    input_queue = asyncio.Queue()

    with manager_agent.override(model=FunctionModel(stream_function=inspect_history)):
        # Turn 1: no history
        history = None
        new_history = None
        async with asyncio.timeout(5):
            async for event in run_manager_pipeline("hello", input_queue, message_history=history):
                if isinstance(event, AgentComplete) and event.new_history:
                    new_history = event.new_history

        assert new_history is not None, "Turn 1 should produce history"

        # Turn 2: pass history from turn 1
        async with asyncio.timeout(5):
            async for event in run_manager_pipeline("follow up", input_queue, message_history=new_history):
                pass

    # Turn 1 sees only the system prompt + user message (no prior history)
    # Turn 2 sees prior messages + new user message — should be more
    assert len(seen_histories) == 2
    assert seen_histories[1] > seen_histories[0], (
        f"Turn 2 should see more messages than turn 1: {seen_histories}"
    )
