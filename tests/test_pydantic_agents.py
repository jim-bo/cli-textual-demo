import pytest
from cli_textual.agents.orchestrators import run_procedural_pipeline, run_manager_pipeline
from cli_textual.core.chat_events import (
    AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete
)

@pytest.mark.asyncio
async def test_procedural_pipeline_flow():
    """Verify that the procedural pipeline yields the expected sequence of events."""
    events = []
    async for event in run_procedural_pipeline("test prompt"):
        events.append(event)
    
    # Assert sequence of event types
    assert any(isinstance(e, AgentThinking) for e in events)
    assert any(isinstance(e, AgentToolStart) and e.tool_name == "study_resolver" for e in events)
    assert any(isinstance(e, AgentToolEnd) and e.tool_name == "study_resolver" for e in events)
    assert any(isinstance(e, AgentStreamChunk) for e in events)
    assert isinstance(events[-1], AgentComplete)

@pytest.mark.asyncio
async def test_manager_pipeline_flow():
    """Verify that the manager pipeline initializes and completes."""
    events = []
    async for event in run_manager_pipeline("test prompt"):
        events.append(event)
    
    # Manager pipeline using TestModel won't call tools unless configured,
    # but it should at least think and complete.
    assert any(isinstance(e, AgentThinking) for e in events)
    assert isinstance(events[-1], AgentComplete)
