"""Tests for MCP (Model Context Protocol) client support.

Covers config parsing (no network), the SAFE_MODE gate, and an end-to-end tool
call against a hermetic in-process FastMCP stdio server — asserting the MCP tool
actually executes and emits the standard AgentToolStart/Output/End lifecycle via
the ``process_tool_call`` hook in ``agents/mcp.py``.

Per the repo conventions: ``FunctionModel`` only (never ``TestModel``), 5s
timeout. MCP tool calls are emitted from the model as ``DeltaToolCall`` deltas
because ``run_pipeline`` drives the streaming event loop.
"""
import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp")  # server side used by the hermetic fixture

from pydantic_ai.mcp import (  # noqa: E402
    MCPServerSSE,
    MCPServerStdio,
    MCPServerStreamableHTTP,
)
from pydantic_ai.messages import ToolReturnPart  # noqa: E402
from pydantic_ai.models.function import DeltaToolCall, FunctionModel  # noqa: E402

import cli_textual.agents.manager as mgr  # noqa: E402
from cli_textual.agents.manager import build_agent, run_pipeline  # noqa: E402
from cli_textual.agents.mcp import (  # noqa: E402
    _emit_events,
    external_entries,
    get_mcp_servers,
    import_to_user_config,
    load_mcp_servers,
    reset_mcp_servers,
    set_mcp_servers,
    user_config_path,
)
from cli_textual.core.chat_events import (  # noqa: E402
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
)


@pytest.fixture(autouse=True)
def _reset_mcp(tmp_path_factory, monkeypatch):
    """Isolate the process-wide server list and config scopes per test.

    - Resets the process-wide server list. These tests call ``build_agent()``
      directly (never ``get_agent()``), so they never touch the manager-agent
      singleton — important, because other test modules bind ``manager_agent``
      at import and resetting it here would make their ``.override()`` calls miss.
    - Points ``XDG_CONFIG_HOME`` at an empty dir so the user-scope config never
      leaks in from the developer's real ``~/.config`` (tests opt in explicitly).
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg")))
    reset_mcp_servers()
    yield
    reset_mcp_servers()


# ---------------------------------------------------------------------------
# Config parsing (no network)
# ---------------------------------------------------------------------------

def test_load_mcp_servers_parses_each_transport(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "env": {"X": "1"}},
        "remote": {"url": "https://example.com/mcp"},
        "events": {"url": "https://example.com/sse", "type": "sse"},
    }}))
    servers = load_mcp_servers(tmp_path / ".mcp.json")
    by_id = {s.id: s for s in servers}
    assert isinstance(by_id["fetch"], MCPServerStdio)
    assert by_id["fetch"].command == "uvx"
    assert by_id["fetch"].args == ["mcp-server-fetch"]
    assert isinstance(by_id["remote"], MCPServerStreamableHTTP)
    assert isinstance(by_id["events"], MCPServerSSE)
    # Every server routes through the event-emitting hook.
    assert all(s.process_tool_call is _emit_events for s in servers)


def test_load_mcp_servers_missing_file_is_not_an_error(tmp_path):
    assert load_mcp_servers(tmp_path / "nope.json") == []


def test_load_mcp_servers_skips_bad_entry_keeps_good(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "ok": {"command": "true", "args": []},
        "bad": {"nonsense": 1},  # neither command nor url -> skipped, not raised
    }}))
    servers = load_mcp_servers(tmp_path / ".mcp.json")
    assert [s.id for s in servers] == ["ok"]


def test_load_mcp_servers_merges_programmatic_extra(tmp_path):
    extra = MCPServerStdio(command="true", args=[], id="prog")
    servers = load_mcp_servers(tmp_path / "nope.json", extra=[extra])
    assert [s.id for s in servers] == ["prog"]


def test_load_mcp_servers_expands_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_TEST_TOKEN", "s3cret")
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "remote": {"url": "https://example.com/mcp",
                   "headers": {"Authorization": "Bearer ${MCP_TEST_TOKEN}"}},
    }}))
    server = load_mcp_servers(tmp_path / ".mcp.json")[0]
    assert server.headers["Authorization"] == "Bearer s3cret"


# ---------------------------------------------------------------------------
# B: user scope + precedence
# ---------------------------------------------------------------------------

def test_user_scope_merges_with_project_which_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    user_file = user_config_path()
    user_file.parent.mkdir(parents=True)
    user_file.write_text(json.dumps({"mcpServers": {
        "shared": {"command": "user-cmd", "args": []},
        "useronly": {"command": "u", "args": []},
    }}))
    project = tmp_path / ".mcp.json"
    project.write_text(json.dumps({"mcpServers": {
        "shared": {"command": "project-cmd", "args": []},
        "projonly": {"command": "p", "args": []},
    }}))
    by_id = {s.id: s for s in load_mcp_servers(project)}
    assert set(by_id) == {"shared", "useronly", "projonly"}
    assert by_id["shared"].command == "project-cmd"  # project overrides user


def test_user_scope_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    user_file = user_config_path()
    user_file.parent.mkdir(parents=True)
    user_file.write_text(json.dumps({"mcpServers": {"u": {"command": "x", "args": []}}}))
    assert load_mcp_servers(tmp_path / "none.json", user_scope=False) == []


# ---------------------------------------------------------------------------
# C: opt-in import / discovery from Claude Code + Gemini CLI
# ---------------------------------------------------------------------------

def test_discover_gemini_normalizes_transports(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    gem = tmp_path / ".gemini"
    gem.mkdir()
    (gem / "settings.json").write_text(json.dumps({"mcpServers": {
        "local": {"command": "godoctor", "args": ["-x"]},
        "httpsrv": {"httpUrl": "http://localhost:3000/mcp", "headers": {"A": "b"}},
        "ssesrv": {"url": "http://localhost:4000/sse"},
    }}))
    by_id = {s.id: s for s in load_mcp_servers(tmp_path / "none.json", discover=["gemini"])}
    assert isinstance(by_id["local"], MCPServerStdio)
    assert isinstance(by_id["httpsrv"], MCPServerStreamableHTTP)  # httpUrl -> streamable
    assert isinstance(by_id["ssesrv"], MCPServerSSE)              # gemini url -> SSE


def test_discover_claude_includes_user_and_project_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(json.dumps({
        "mcpServers": {"usersrv": {"command": "u", "args": []}},
        "projects": {str(Path.cwd()): {"mcpServers": {
            "projsrv": {"type": "http", "url": "https://example.com/mcp"}}}},
    }))
    by_id = {s.id: s for s in load_mcp_servers(tmp_path / "none.json", discover=["claude"])}
    assert isinstance(by_id["usersrv"], MCPServerStdio)
    assert isinstance(by_id["projsrv"], MCPServerStreamableHTTP)


def test_external_entries_unknown_source_raises():
    with pytest.raises(ValueError):
        external_entries("cursor")


def test_import_to_user_config_writes_then_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {
        "a": {"command": "x", "args": []},
        "b": {"command": "y", "args": []},
    }}))
    added, skipped = import_to_user_config("claude")
    assert set(added) == {"a", "b"} and skipped == []
    data = json.loads(user_config_path().read_text())
    assert set(data["mcpServers"]) == {"a", "b"}
    # Re-importing keeps existing entries instead of clobbering them.
    added2, skipped2 = import_to_user_config("claude")
    assert added2 == [] and set(skipped2) == {"a", "b"}


# ---------------------------------------------------------------------------
# Agent attachment + SAFE_MODE gate
# ---------------------------------------------------------------------------

def _toolset_ids(agent) -> set[str]:
    return {getattr(t, "id", None) for t in agent.toolsets}


def test_build_agent_attaches_mcp_toolsets():
    set_mcp_servers([MCPServerStdio(command="true", args=[], id="demo")])
    assert "demo" in _toolset_ids(build_agent())


def test_safe_mode_withholds_mcp_toolsets():
    set_mcp_servers([MCPServerStdio(command="true", args=[], id="demo")])
    mgr.SAFE_MODE = True
    try:
        assert "demo" not in _toolset_ids(build_agent())
    finally:
        mgr.SAFE_MODE = False


# ---------------------------------------------------------------------------
# End-to-end: hermetic FastMCP stdio server
# ---------------------------------------------------------------------------

_SERVER_SRC = textwrap.dedent(
    """
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("testsrv")

    @mcp.tool()
    def echo(text: str) -> str:
        return f"echo: {text}"

    @mcp.tool()
    def boom() -> str:
        raise ValueError("kaboom")

    if __name__ == "__main__":
        mcp.run()
    """
)


@pytest.fixture
def mcp_server_script(tmp_path) -> Path:
    script = tmp_path / "srv.py"
    script.write_text(_SERVER_SRC)
    return script


def _stdio_server(script: Path) -> MCPServerStdio:
    return MCPServerStdio(
        command=sys.executable,
        args=[str(script)],
        id="test",
        tool_prefix=None,
        process_tool_call=_emit_events,
    )


def _call_tool_model(tool_name: str, json_args: str) -> FunctionModel:
    """Model that calls ``tool_name`` once, then replies with text."""
    async def stream_fn(messages, info):
        returned = any(
            isinstance(p, ToolReturnPart)
            for m in messages
            for p in getattr(m, "parts", [])
        )
        if not returned:
            yield {0: DeltaToolCall(name=tool_name, json_args=json_args)}
        else:
            yield "done"

    return FunctionModel(stream_function=stream_fn)


async def _drive(agent, model) -> list:
    events = []
    async with agent:  # enter the MCP connection (starts the subprocess)
        with agent.override(model=model):
            async with asyncio.timeout(20):
                async for ev in run_pipeline(agent, "go", asyncio.Queue()):
                    events.append(ev)
    return events


@pytest.mark.asyncio
async def test_mcp_tool_call_executes_and_emits_lifecycle(mcp_server_script):
    set_mcp_servers([_stdio_server(mcp_server_script)])
    events = await _drive(build_agent(), _call_tool_model("echo", '{"text": "hi"}'))

    kinds = [type(e).__name__ for e in events]
    assert kinds.index("AgentToolStart") < kinds.index("AgentToolOutput") < kinds.index("AgentToolEnd")
    out = next(e for e in events if isinstance(e, AgentToolOutput))
    assert out.content == "echo: hi"  # the tool actually ran
    assert out.is_error is False
    assert next(e for e in events if isinstance(e, AgentToolStart)).tool_name == "echo"
    assert next(e for e in events if isinstance(e, AgentToolEnd)).result == "ok"


@pytest.mark.asyncio
async def test_mcp_tool_error_emits_error_event(mcp_server_script):
    set_mcp_servers([_stdio_server(mcp_server_script)])
    events = await _drive(build_agent(), _call_tool_model("boom", "{}"))

    out = next(e for e in events if isinstance(e, AgentToolOutput))
    assert out.is_error is True
    assert "kaboom" in out.content
    assert next(e for e in events if isinstance(e, AgentToolEnd)).result == "error"
