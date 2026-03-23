import asyncio
import pytest
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.test import TestModel
from cli_textual.agents.orchestrators import run_procedural_pipeline, run_manager_pipeline, manager_agent
from cli_textual.agents.specialists import intent_resolver, data_validator, result_generator
from cli_textual.core.chat_events import (
    AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete,
    AgentRequiresUserInput
)

@pytest.mark.asyncio
async def test_procedural_pipeline_flow():
    """Verify that the procedural pipeline yields the expected sequence of events."""
    events = []
    with intent_resolver.override(model=TestModel()), \
         data_validator.override(model=TestModel()), \
         result_generator.override(model=TestModel()):
        async for event in run_procedural_pipeline("test prompt"):
            events.append(event)

    # Assert sequence of event types
    assert any(isinstance(e, AgentThinking) for e in events)
    assert any(isinstance(e, AgentToolStart) and e.tool_name == "intent_resolver" for e in events)
    assert any(isinstance(e, AgentToolEnd) and e.tool_name == "intent_resolver" for e in events)
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)

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
