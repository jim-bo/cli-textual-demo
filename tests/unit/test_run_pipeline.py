"""Tests for the generic ``run_pipeline(agent, …)`` entry point and the
``build_agent(tools=[…])`` factory introduced for multi-module
orchestrations."""

import asyncio

import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cli_textual.agents.manager import (
    _BUILTIN_TOOLS,
    build_agent,
    get_agent,
    run_manager_pipeline,
    run_pipeline,
)
from cli_textual.core.chat_events import (
    AgentComplete,
    AgentStreamChunk,
    AgentThinking,
)
from cli_textual.tools.base import ToolResult
from cli_textual.tools.registry import clear_extra_tools, register_tool


def _tool_names(agent) -> set[str]:
    """Return the set of tool names registered on ``agent``."""
    return set(agent._function_toolset.tools.keys())


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_pipeline_with_manager_agent_matches_run_manager_pipeline():
    """``run_pipeline(get_agent(), …)`` should produce the same event
    shape as the legacy ``run_manager_pipeline`` wrapper."""

    async def fixed_response(messages: list[ModelMessage], agent_info: AgentInfo):
        yield "ok"

    async def collect(pipeline):
        out = []
        async for ev in pipeline:
            out.append(ev)
        return out

    agent = get_agent()
    input_queue_a = asyncio.Queue()
    input_queue_b = asyncio.Queue()

    with agent.override(model=FunctionModel(stream_function=fixed_response)):
        async with asyncio.timeout(5):
            events_generic = await collect(run_pipeline(agent, "hi", input_queue_a))
        async with asyncio.timeout(5):
            events_legacy = await collect(run_manager_pipeline("hi", input_queue_b))

    # Both should start with thinking and end with complete.
    assert any(isinstance(e, AgentThinking) for e in events_generic)
    assert isinstance(events_generic[-1], AgentComplete)
    assert any(isinstance(e, AgentThinking) for e in events_legacy)
    assert isinstance(events_legacy[-1], AgentComplete)

    # Same shape of event types in the same order.
    assert [type(e).__name__ for e in events_generic] == [
        type(e).__name__ for e in events_legacy
    ]


@pytest.mark.asyncio
async def test_run_pipeline_accepts_caller_supplied_agent():
    """Passing a freshly-built filtered agent should work end-to-end."""

    async def fixed_response(messages: list[ModelMessage], agent_info: AgentInfo):
        yield "filtered agent reply"

    agent = build_agent(tools=["web_fetch"])
    input_queue = asyncio.Queue()
    events = []

    with agent.override(model=FunctionModel(stream_function=fixed_response)):
        async with asyncio.timeout(5):
            async for ev in run_pipeline(agent, "hello", input_queue):
                events.append(ev)

    assert isinstance(events[-1], AgentComplete)
    stream_chunks = [e for e in events if isinstance(e, AgentStreamChunk)]
    assert "filtered agent reply" in "".join(c.text for c in stream_chunks)


# ---------------------------------------------------------------------------
# build_agent
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _cleanup_registry():
    """Ensure the extra-tools registry is empty before and after each test."""
    clear_extra_tools()
    yield
    clear_extra_tools()


def test_build_agent_default_has_all_builtin_tools():
    """Default ``build_agent()`` should attach every built-in (modulo SAFE_MODE)."""
    agent = build_agent()
    names = _tool_names(agent)
    # All built-ins should be present; this test runs without SAFE_MODE set.
    assert set(_BUILTIN_TOOLS) <= names


def test_build_agent_default_includes_registered_extras():
    """Tools registered via ``register_tool`` show up in the default build."""

    async def my_extra_tool(query: str) -> ToolResult:
        """An extra tool for testing."""
        return ToolResult(output=f"queried {query}")

    register_tool(my_extra_tool)

    agent = build_agent()
    names = _tool_names(agent)
    assert "my_extra_tool" in names
    assert set(_BUILTIN_TOOLS) <= names


def test_build_agent_with_filter_only_registers_named_tools():
    """``tools=[…]`` should narrow the roster to exactly those names."""

    async def planner_tool(_x: str) -> ToolResult:
        """Planner-only tool."""
        return ToolResult(output="planned")

    async def analyst_tool(_x: str) -> ToolResult:
        """Analyst-only tool."""
        return ToolResult(output="analyzed")

    register_tool(planner_tool)
    register_tool(analyst_tool)

    agent = build_agent(tools=["web_fetch", "planner_tool"])
    names = _tool_names(agent)

    assert names == {"web_fetch", "planner_tool"}
    assert "analyst_tool" not in names
    assert "read_file" not in names  # other built-ins excluded too


def test_build_agent_empty_filter_registers_nothing():
    """``tools=[]`` produces a no-tool agent (legitimate edge case)."""
    agent = build_agent(tools=[])
    assert _tool_names(agent) == set()


def test_build_agent_unknown_tool_raises():
    """Unknown tool names should raise ``ValueError`` mentioning them."""
    with pytest.raises(ValueError, match="nope"):
        build_agent(tools=["nope"])


def test_build_agent_unknown_tool_lists_all_unknowns():
    """All unknown names should appear in the error to make typo-spotting easy."""
    with pytest.raises(ValueError) as excinfo:
        build_agent(tools=["web-fetch", "read_files"])
    msg = str(excinfo.value)
    assert "web-fetch" in msg
    assert "read_files" in msg


def test_build_agent_does_not_mutate_singleton():
    """``build_agent`` must not affect ``get_agent()``'s cached singleton."""
    singleton = get_agent()
    singleton_tools = _tool_names(singleton)

    fresh = build_agent(tools=["web_fetch"])
    assert _tool_names(fresh) == {"web_fetch"}
    # Singleton untouched.
    assert _tool_names(get_agent()) == singleton_tools
    assert get_agent() is singleton
