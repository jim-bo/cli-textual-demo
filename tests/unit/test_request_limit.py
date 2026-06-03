"""The agentic step budget: run_pipeline must bound the tool loop by
``request_limit`` (pydantic-ai's default of 50 is too low for long
iterate-against-tests runs) and terminate gracefully when it's hit."""
import asyncio

import pytest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

import cli_textual.agents.manager as manager
from cli_textual.agents.manager import build_agent, run_pipeline
from cli_textual.core.chat_events import AgentComplete, AgentToolStart
from cli_textual.tools.base import ToolResult
from cli_textual.tools.registry import clear_extra_tools, register_tool

pytestmark = pytest.mark.timeout(5)


@pytest.fixture(autouse=True)
def _clean():
    clear_extra_tools()
    yield
    clear_extra_tools()


async def _always_calls_tool(messages, info: AgentInfo):
    # Every model turn emits one call to `loop_tool` -> would loop forever
    # without a request budget.
    yield {0: DeltaToolCall(name="loop_tool", json_args="{}", tool_call_id="c1")}


def test_default_request_limit_is_above_pydantic_default():
    # pydantic-ai's own default request_limit is only 50 — too low for long
    # iterate-against-tests runs; our default raises it (env-overridable via
    # CLI_TEXTUAL_REQUEST_LIMIT).
    assert manager.REQUEST_LIMIT >= 100


@pytest.mark.asyncio
async def test_request_limit_bounds_tool_loop():
    async def loop_tool() -> ToolResult:
        """A no-op tool the model calls in a loop."""
        return ToolResult(output="ok")

    register_tool(loop_tool)
    agent = build_agent(tools=["loop_tool"])
    input_queue: asyncio.Queue = asyncio.Queue()

    tool_starts = 0
    saw_complete = False
    with agent.override(model=FunctionModel(stream_function=_always_calls_tool)):
        async with asyncio.timeout(5):
            async for ev in run_pipeline(agent, "go", input_queue, request_limit=3):
                if isinstance(ev, AgentToolStart):
                    tool_starts += 1
                if isinstance(ev, AgentComplete):
                    saw_complete = True

    # It looped (more than once) but the budget bounded it and it ended cleanly.
    assert saw_complete
    assert 1 <= tool_starts <= 4  # ~request_limit, not a runaway
