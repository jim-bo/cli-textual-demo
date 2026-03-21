import asyncio
import pytest
from cli_textual.agents.orchestrators import run_procedural_pipeline, run_manager_pipeline
from cli_textual.core.chat_events import (
    AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete,
    AgentRequiresUserInput
)

@pytest.mark.asyncio
async def test_procedural_pipeline_flow():
    """Verify that the procedural pipeline yields the expected sequence of events."""
    events = []
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
    events = []
    input_queue = asyncio.Queue()
    
    # We wrap this in a timeout to prevent hanging
    try:
        async with asyncio.timeout(5):
            pipeline = run_manager_pipeline("test prompt", input_queue)
            async for event in pipeline:
                events.append(event)
                # If the TestModel randomly decides to call a tool (like selection), unblock it
                if isinstance(event, AgentRequiresUserInput):
                    await input_queue.put("mock selection")
    except asyncio.TimeoutError:
        pytest.fail("test_manager_pipeline_flow timed out - likely deadlocked on queue.get()")
    
    # Manager pipeline using TestModel should at least think and complete.
    assert any(isinstance(e, AgentThinking) for e in events)
    assert isinstance(events[-1], AgentComplete)
