"""Tests for the library extension API: tool registry, model override,
lazy agent construction, command packages, ChatApp constructor, public exports.
"""
import asyncio
import sys
import types

import pytest

pytestmark = pytest.mark.timeout(5)

import cli_textual.agents.manager as mgr
import cli_textual.agents.model as model_mod
from cli_textual.core.chat_events import (
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
    ChatDeps,
)
from cli_textual.tools.base import ToolResult
from cli_textual.tools.registry import (
    clear_extra_tools,
    get_extra_tools,
    register_tool,
)


@pytest.fixture(autouse=True)
def _reset_state():
    # Save the pre-existing agent so other test modules that captured
    # ``from cli_textual.agents.manager import manager_agent`` at import time
    # still see the same instance after this test finishes.
    saved = mgr._agent_instance
    clear_extra_tools()
    model_mod.set_model(None)
    mgr._reset_agent()
    yield
    clear_extra_tools()
    model_mod.set_model(None)
    mgr._agent_instance = saved


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def test_register_tool_appends_to_registry():
    async def echo(text: str) -> ToolResult:
        """Echo the input."""
        return ToolResult(output=text)

    register_tool(echo)
    assert echo in get_extra_tools()


def test_registered_tool_appears_in_built_agent():
    async def echo(text: str) -> ToolResult:
        """Echo the input."""
        return ToolResult(output=text)

    register_tool(echo)
    agent = mgr.get_agent()
    assert "echo" in agent._function_toolset.tools


def test_wrapped_tool_preserves_parameter_schema():
    async def query(sql: str, limit: int = 10) -> ToolResult:
        """Run a SQL query."""
        return ToolResult(output=f"{sql}:{limit}")

    register_tool(query)
    agent = mgr.get_agent()
    tool = agent._function_toolset.tools["query"]
    # pydantic-ai derives the JSON schema from the wrapper's signature +
    # annotations; check that pure_fn's params made it through.
    schema = tool.function_schema.json_schema
    assert "sql" in schema["properties"]
    assert "limit" in schema["properties"]
    assert schema["properties"]["sql"]["type"] == "string"


def test_wrapped_tool_catches_exceptions():
    async def boom() -> ToolResult:
        """Explodes."""
        raise RuntimeError("nope")

    register_tool(boom)
    agent = mgr.get_agent()
    tool = agent._function_toolset.tools["boom"]

    queue: asyncio.Queue = asyncio.Queue()
    deps = ChatDeps(event_queue=queue, input_queue=asyncio.Queue())

    class _Ctx:
        def __init__(self, deps):
            self.deps = deps

    asyncio.run(tool.function(_Ctx(deps)))
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    # Start → Output(is_error=True) → End("error") — full lifecycle even on crash
    assert [type(e) for e in events] == [AgentToolStart, AgentToolOutput, AgentToolEnd]
    assert events[1].is_error is True
    assert "RuntimeError" in events[1].content
    assert events[2].result == "error"


def test_register_tool_rejects_sync_function():
    def not_async(x: str) -> ToolResult:
        return ToolResult(output=x)

    with pytest.raises(TypeError, match="async"):
        register_tool(not_async)


def test_register_tool_is_idempotent_for_same_fn():
    async def echo(x: str) -> ToolResult:
        return ToolResult(output=x)

    register_tool(echo)
    register_tool(echo)  # no-op, no raise
    assert get_extra_tools().count(echo) == 1


def test_register_tool_rejects_name_collision():
    async def alpha() -> ToolResult:
        return ToolResult(output="a")

    alpha.__name__ = "same_name"
    register_tool(alpha)

    async def beta() -> ToolResult:
        return ToolResult(output="b")

    beta.__name__ = "same_name"
    with pytest.raises(ValueError, match="already registered"):
        register_tool(beta)


def test_wrapped_tool_emits_lifecycle_events():
    async def boom(msg: str) -> ToolResult:
        """Always errors."""
        return ToolResult(output=f"err: {msg}", is_error=True)

    register_tool(boom)
    agent = mgr.get_agent()
    tool = agent._function_toolset.tools["boom"]

    queue: asyncio.Queue = asyncio.Queue()
    deps = ChatDeps(event_queue=queue, input_queue=asyncio.Queue())

    class _Ctx:
        def __init__(self, deps):
            self.deps = deps

    result = asyncio.run(tool.function(_Ctx(deps), msg="hi"))
    assert result == "err: hi"

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert [type(e) for e in events] == [AgentToolStart, AgentToolOutput, AgentToolEnd]
    assert events[0].tool_name == "boom"
    assert events[0].args == {"msg": "hi"}
    assert events[1].is_error is True
    assert events[2].result == "error"


# ---------------------------------------------------------------------------
# Model override
# ---------------------------------------------------------------------------

def test_set_model_overrides_get_model():
    from pydantic_ai.models.test import TestModel

    sentinel = TestModel()
    model_mod.set_model(sentinel)
    assert model_mod.get_model() is sentinel


def test_set_model_accepts_string():
    from pydantic_ai.models.test import TestModel

    model_mod.set_model("test")
    assert isinstance(model_mod.get_model(), TestModel)


# ---------------------------------------------------------------------------
# Lazy agent construction
# ---------------------------------------------------------------------------

def test_agent_is_lazy():
    mgr._reset_agent()
    assert mgr._agent_instance is None
    mgr.get_agent()
    assert mgr._agent_instance is not None


def test_manager_agent_attribute_shim_still_works():
    mgr._reset_agent()
    # Accessing the legacy attribute triggers the lazy build.
    agent = mgr.manager_agent
    assert agent is mgr._agent_instance


# ---------------------------------------------------------------------------
# Command packages
# ---------------------------------------------------------------------------

def test_chatapp_discovers_extra_command_packages(tmp_path, monkeypatch):
    # Build a throwaway package on disk with one SlashCommand subclass.
    pkg_dir = tmp_path / "my_pkg_commands"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "ping.py").write_text(
        "from typing import List\n"
        "from cli_textual.core.command import SlashCommand\n"
        "class PingCommand(SlashCommand):\n"
        "    @property\n"
        "    def name(self): return '/ping'\n"
        "    @property\n"
        "    def description(self): return 'Pong'\n"
        "    async def execute(self, app, args: List[str]):\n"
        "        pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    from cli_textual.core.command import CommandManager
    cm = CommandManager()
    cm.auto_discover("my_pkg_commands")
    assert "/ping" in cm.commands


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def test_public_api_exports():
    import cli_textual

    for name in ("ChatApp", "ToolResult", "register_tool", "SlashCommand", "CommandManager", "ChatDeps"):
        assert hasattr(cli_textual, name), f"cli_textual.{name} missing"
