import asyncio
import inspect
import os
from pathlib import Path
from typing import Any, AsyncGenerator, List

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import TextPart, ThinkingPart

from cli_textual.agents.model import get_model
from cli_textual.agents.prompt_loader import PROMPTS
from cli_textual.core.chat_events import (
    AgentComplete,
    AgentExecuteCommand,
    AgentRequiresUserInput,
    AgentStreamChunk,
    AgentThinking,
    AgentThinkingChunk,
    AgentThinkingComplete,
    AgentToolEnd,
    AgentToolOutput,
    AgentToolStart,
    ChatDeps,
    ChatEvent,
)
from cli_textual.tools.base import ToolResult
from cli_textual.tools.bash import bash_exec as pure_bash_exec
from cli_textual.tools.edit_file import edit_file as pure_edit_file
from cli_textual.tools.glob_tool import glob as pure_glob
from cli_textual.tools.grep import grep as pure_grep
from cli_textual.tools.read_file import read_file as pure_read_file
from cli_textual.tools.registry import get_extra_tools
from cli_textual.tools.todo_write import todo_write as pure_todo_write
from cli_textual.tools.web_fetch import web_fetch as pure_web_fetch
from cli_textual.tools.write_file import write_file as pure_write_file

# ---------------------------------------------------------------------------
# Safe Mode
# ---------------------------------------------------------------------------
SAFE_MODE = os.getenv("SAFE_MODE", "").lower() in ("1", "true", "yes")

# Agentic step budget: max model requests in one pipeline run. pydantic-ai's
# default is 50, too low for long iterate-against-tests coding runs; default
# higher and allow override via env / the run_pipeline arg.
REQUEST_LIMIT = int(os.getenv("CLI_TEXTUAL_REQUEST_LIMIT", "100"))


# Optional library-consumer overrides for the manager system prompt.
# Set via ChatApp(system_prompt=..., system_prompt_append=...).
SYSTEM_PROMPT_OVERRIDE: str | None = None
SYSTEM_PROMPT_APPEND: str | None = None


def _get_system_prompt() -> str:
    if SYSTEM_PROMPT_OVERRIDE is not None:
        base = SYSTEM_PROMPT_OVERRIDE
    else:
        base = PROMPTS['orchestrators']['manager']['system_prompt']
    if SYSTEM_PROMPT_APPEND:
        base += "\n\n" + SYSTEM_PROMPT_APPEND
    if SAFE_MODE:
        base += "\n\n" + PROMPTS['orchestrators']['manager']['safety_preamble']
    return base


# ---------------------------------------------------------------------------
# Built-in tool wrappers (pure logic in cli_textual/tools/)
# ---------------------------------------------------------------------------

async def ask_user_to_select(ctx: RunContext[ChatDeps], prompt: str, options: List[str]) -> str:
    """Show a selection menu in the TUI and WAIT for the user's choice before continuing.

    ALWAYS call this tool when the user's message contains any selection intent:
      - "let me select / choose / pick"
      - "I want to choose / select"
      - "help me pick"
      - "first pick / first choose / first select"
      - any phrasing where the user should decide between options

    This tool PAUSES the agent and BLOCKS until the user makes a choice in the terminal UI.
    You MUST call this BEFORE writing any response that depends on the user's selection.
    The return value is the user's chosen option — use it in your response.

    Args:
        prompt: The question shown above the menu (e.g., "Choose a primary color:")
        options: The list of choices to display (e.g., ["Red", "Blue", "Yellow"])
    """
    await ctx.deps.event_queue.put(AgentRequiresUserInput(tool_name="/select", prompt=prompt, options=options))
    response = await ctx.deps.input_queue.get()
    return response


async def execute_slash_command(ctx: RunContext[ChatDeps], command_name: str, args: List[str] | None = None) -> str:
    """Execute a TUI slash command (e.g. '/clear', '/ls').
    Use this to trigger UI actions or system tools.
    """
    if args is None:
        args = []
    if not command_name.startswith("/"):
        command_name = f"/{command_name}"
    await ctx.deps.event_queue.put(AgentExecuteCommand(command_name=command_name, args=args))
    return f"Command {command_name} triggered in UI."


async def read_file(ctx: RunContext[ChatDeps], path: str, start_line: int = 1, end_line: int | None = None) -> str:
    """Read the contents of a local file, optionally restricted to a line range.

    Args:
        path: File path (relative to CWD or absolute)
        start_line: First line to include, 1-indexed (default: 1)
        end_line: Last line to include (default: read all, capped at 200 lines)
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="read_file", args={"path": path}))
    result = await pure_read_file(path, start_line, end_line, workspace_root=Path.cwd())
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="read_file", content=result.output, is_error=result.is_error))
    status = "error" if result.is_error else "ok"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="read_file", result=status))
    return result.output


async def web_fetch(ctx: RunContext[ChatDeps], url: str) -> str:
    """Fetch the contents of a URL via HTTP GET and return the response body.

    Use this for REST APIs, documentation pages, or any web resource.
    Response body is capped at 8 KB; a truncation note is appended when exceeded.

    Args:
        url: The URL to fetch
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="web_fetch", args={"url": url}))
    result = await pure_web_fetch(url)
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="web_fetch", content=result.output, is_error=result.is_error))
    status = "error" if result.is_error else "ok"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="web_fetch", result=status))
    return result.output


async def bash_exec(ctx: RunContext[ChatDeps], command: str, working_dir: str = ".") -> str:
    """Execute a shell command and stream its output to the UI in real time.

    Use this to run scripts, inspect the system, process files, or perform any
    shell operation. stdout and stderr are merged and streamed as they arrive.
    Output is capped at 8 KB; a truncation note is appended when exceeded.

    Args:
        command: The shell command to run (passed to /bin/sh)
        working_dir: Working directory for the command (default: current directory)
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="bash_exec", args={"command": command}))
    result = await pure_bash_exec(command, working_dir)
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="bash_exec", content=result.output, is_error=result.is_error))
    status = "error" if result.is_error else f"exit {result.exit_code}"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="bash_exec", result=status))
    return result.output


async def write_file(ctx: RunContext[ChatDeps], path: str, content: str) -> str:
    """Create or overwrite a file with the given contents.

    Parent directories are created as needed. Use this to author new files or
    fully replace an existing one; for a small in-place change, prefer
    ``edit_file``.

    Args:
        path: File path (relative to CWD or absolute)
        content: Full file contents to write
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="write_file", args={"path": path}))
    result = await pure_write_file(path, content, workspace_root=Path.cwd())
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="write_file", content=result.output, is_error=result.is_error))
    status = "error" if result.is_error else "ok"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="write_file", result=status))
    return result.output


async def edit_file(
    ctx: RunContext[ChatDeps],
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Replace an exact string in a file (in-place edit).

    Find ``old_string`` and replace it with ``new_string``. Include enough
    surrounding context in ``old_string`` to match exactly one location, or set
    ``replace_all=True`` to replace every occurrence. Pass ``new_string=""`` to
    delete the matched text. Errors if ``old_string`` is not found, or if it
    matches multiple times and ``replace_all`` is False.

    Args:
        path: File path (relative to CWD or absolute)
        old_string: Exact text to find
        new_string: Replacement text
        replace_all: Replace every occurrence instead of requiring a unique match
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="edit_file", args={"path": path}))
    result = await pure_edit_file(path, old_string, new_string, replace_all=replace_all, workspace_root=Path.cwd())
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="edit_file", content=result.output, is_error=result.is_error))
    status = "error" if result.is_error else "ok"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="edit_file", result=status))
    return result.output


async def grep(
    ctx: RunContext[ChatDeps],
    pattern: str,
    path: str = ".",
    ignore_case: bool = False,
    max_results: int = 100,
) -> str:
    """Search file contents for a regular expression (returns ``file:line: text``).

    Recursively searches under ``path``, skipping VCS/build dirs and binary
    files. Prefer this over running ``grep`` through the shell — it returns
    clean, capped output.

    Args:
        pattern: Regular expression to search for
        path: File or directory to search under (default: current directory)
        ignore_case: Case-insensitive match when True
        max_results: Stop after this many matching lines (default 100)
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="grep", args={"pattern": pattern, "path": path}))
    result = await pure_grep(pattern, path, ignore_case=ignore_case, max_results=max_results, workspace_root=Path.cwd())
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="grep", content=result.output, is_error=result.is_error))
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="grep", result="error" if result.is_error else "ok"))
    return result.output


async def glob(ctx: RunContext[ChatDeps], pattern: str, path: str = ".", max_results: int = 100) -> str:
    """Find files matching a glob pattern (supports ``**``); newest first.

    Prefer this over running ``find`` through the shell.

    Args:
        pattern: Glob pattern, e.g. ``**/*.py`` or ``src/**/test_*.py``
        path: Directory to search under (default: current directory)
        max_results: Cap on number of paths returned (default 100)
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="glob", args={"pattern": pattern, "path": path}))
    result = await pure_glob(pattern, path, max_results=max_results, workspace_root=Path.cwd())
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="glob", content=result.output, is_error=result.is_error))
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="glob", result="error" if result.is_error else "ok"))
    return result.output


async def todo_write(ctx: RunContext[ChatDeps], todos: list[dict[str, str]]) -> str:
    """Record/replace your todo list and render it as a checklist.

    Pass the FULL list every call (it replaces the previous one). Use this to
    plan a multi-step task and track progress as you work.

    Args:
        todos: list of ``{"content": <str>, "status": <pending|in_progress|completed>}``
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="todo_write", args={"count": len(todos) if isinstance(todos, list) else 0}))
    result = await pure_todo_write(todos)
    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="todo_write", content=result.output, is_error=result.is_error))
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="todo_write", result="error" if result.is_error else "ok"))
    return result.output


# ---------------------------------------------------------------------------
# Extra-tool adapter: wraps a pure ToolResult function into a pydantic-ai tool
# ---------------------------------------------------------------------------

def _wrap_and_register(agent: Agent, pure_fn) -> None:
    """Generate a pydantic-ai tool wrapper for a pure ``ToolResult`` function.

    The wrapper emits the standard ``AgentToolStart`` → ``AgentToolOutput`` →
    ``AgentToolEnd`` lifecycle so third-party tools render identically to
    built-ins. ``pure_fn`` must be an ``async`` function returning a
    ``ToolResult``; its ``__name__`` and ``__doc__`` become the tool name and
    description seen by the LLM.
    """
    name = pure_fn.__name__

    async def wrapper(ctx: RunContext[ChatDeps], **kwargs) -> str:
        await ctx.deps.event_queue.put(AgentToolStart(tool_name=name, args=kwargs))
        try:
            result = await pure_fn(**kwargs)
            if not isinstance(result, ToolResult):
                result = ToolResult(
                    output=f"tool {name!r} returned {type(result).__name__}, expected ToolResult",
                    is_error=True,
                )
        except Exception as exc:  # noqa: BLE001 — surface any user-tool failure cleanly
            result = ToolResult(output=f"{type(exc).__name__}: {exc}", is_error=True)

        await ctx.deps.event_queue.put(
            AgentToolOutput(tool_name=name, content=result.output, is_error=result.is_error)
        )
        status = "error" if result.is_error else "ok"
        await ctx.deps.event_queue.put(AgentToolEnd(tool_name=name, result=status))
        return result.output

    # Expose pure_fn's parameter schema to pydantic-ai by constructing a
    # synthetic signature: (ctx: RunContext[ChatDeps], *pure_fn_params).
    # pydantic-ai uses inspect.signature(wrapper) to build the tool's JSON
    # schema, so without this the LLM would see only ``**kwargs``.
    original_sig = inspect.signature(pure_fn)
    ctx_param = inspect.Parameter(
        "ctx",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=RunContext[ChatDeps],
    )
    wrapper.__signature__ = original_sig.replace(
        parameters=[ctx_param, *original_sig.parameters.values()]
    )
    # pydantic-ai calls get_type_hints(fn), which reads __annotations__ — not
    # the synthetic __signature__. Merge the pure function's annotations so
    # each parameter resolves to its declared type.
    wrapper.__annotations__ = {
        "ctx": RunContext[ChatDeps],
        **getattr(pure_fn, "__annotations__", {}),
    }
    wrapper.__name__ = name
    wrapper.__doc__ = pure_fn.__doc__
    wrapper.__wrapped__ = pure_fn
    agent.tool(wrapper)


# ---------------------------------------------------------------------------
# Agent factory + lazy singleton
# ---------------------------------------------------------------------------
_BUILTIN_TOOLS = {
    "ask_user_to_select": ask_user_to_select,
    "execute_slash_command": execute_slash_command,
    "read_file": read_file,
    "web_fetch": web_fetch,
    "bash_exec": bash_exec,
    "write_file": write_file,
    "edit_file": edit_file,
    "grep": grep,
    "glob": glob,
    "todo_write": todo_write,
}

# Tools that mutate the local filesystem (or shell out) — disabled in SAFE_MODE
# so a publicly hosted instance stays read-only.
_UNSAFE_TOOLS = {"bash_exec", "write_file", "edit_file"}

_agent_instance: Agent | None = None


def build_agent(tools: list[str] | None = None) -> Agent:
    """Construct a fresh ``pydantic_ai.Agent``.

    Args:
        tools: When ``None`` (default), attach every built-in tool
            (``bash_exec`` is skipped in ``SAFE_MODE``) plus every tool
            registered via :func:`cli_textual.tools.registry.register_tool`.
            When a list of names, attach only the named tools — useful
            for role-specialized agents in multi-module orchestrations.
            Names are the function's ``__name__`` (the same identity
            ``register_tool`` uses).

    Returns:
        A fresh ``Agent``; this never mutates the manager singleton.

    Raises:
        ValueError: if ``tools`` references a name that matches neither a
            built-in nor a registered extra tool.
    """
    extras = {fn.__name__: fn for fn in get_extra_tools()}

    if tools is not None:
        known = set(_BUILTIN_TOOLS) | set(extras)
        unknown = [name for name in tools if name not in known]
        if unknown:
            raise ValueError(
                f"build_agent: unknown tool name(s) {unknown!r}; "
                f"known tools are {sorted(known)!r}"
            )

    def _enabled(name: str) -> bool:
        if name in _UNSAFE_TOOLS and SAFE_MODE:
            return False
        if tools is None:
            return True
        return name in tools

    agent = Agent(
        get_model(),
        deps_type=ChatDeps,
        system_prompt=_get_system_prompt(),
    )

    # Built-in tools (registered directly — they already speak the event protocol)
    for name, fn in _BUILTIN_TOOLS.items():
        if _enabled(name):
            agent.tool(fn)

    # Extra tools (wrapped to emit the AgentToolStart/Output/End lifecycle)
    for name, fn in extras.items():
        if _enabled(name):
            _wrap_and_register(agent, fn)

    return agent


def _build_agent() -> Agent:
    """Back-compat alias used by :func:`get_agent`. Returns an agent with all tools."""
    return build_agent()


def get_agent() -> Agent:
    """Return the lazily-constructed manager agent singleton."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = _build_agent()
    return _agent_instance


def _reset_agent() -> None:
    """Drop the cached singleton so the next ``get_agent()`` rebuilds it.

    Intended for tests and for ``ChatApp.__init__`` when overrides arrive
    after an earlier build.
    """
    global _agent_instance
    _agent_instance = None


def __getattr__(attr: str):
    """PEP 562 shim: ``from cli_textual.agents.manager import manager_agent``
    still works, but the agent is only built on first access.
    """
    if attr == "manager_agent":
        return get_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {attr!r}")


# ---------------------------------------------------------------------------
# Generic streaming pipeline
# ---------------------------------------------------------------------------
async def run_pipeline(
    agent: Agent,
    prompt: str,
    input_queue: asyncio.Queue,
    message_history: List[Any] | None = None,
    session_id: str | None = None,
    request_limit: int | None = None,
) -> AsyncGenerator[ChatEvent, None]:
    """Stream ``ChatEvent``s from a single ``pydantic_ai.Agent`` run.

    The caller supplies the agent so multi-module orchestrations
    (Planner / Analyst / Librarian / Conductor …) can drive
    role-specialized agents through the same event-streaming machinery
    that powers the manager singleton. The ``input_queue`` is read by
    tools that pause for user input (e.g. ``ask_user_to_select``);
    yielded events follow the contract in ``cli_textual.core.chat_events``.

    ``request_limit`` caps the number of model requests in one run (the
    agentic step budget). When ``None``, falls back to ``REQUEST_LIMIT`` (env
    ``CLI_TEXTUAL_REQUEST_LIMIT``, default 100). pydantic-ai's own default is
    only 50, which is too low for long iterate-against-tests coding runs.
    """
    if request_limit is None:
        request_limit = REQUEST_LIMIT
    event_queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)

    await event_queue.put(AgentThinking(message="Agent initializing..."))

    async def run_agent():
        # State for thinking→text transition, shared across the whole run.
        # Unlike the old stream_responses() consumption (which streamed only the
        # final model turn), run_stream_events drives the FULL agentic loop, so
        # tool calls execute even when the model emits text before calling a
        # tool. Tool lifecycle events are emitted by the tool wrappers
        # themselves onto event_queue, so we only map text/thinking deltas here.
        thinking_complete = False
        saw_thinking = False
        full_thinking = ""

        async def on_thinking(text: str) -> None:
            nonlocal saw_thinking, full_thinking
            if not text:
                return
            saw_thinking = True
            full_thinking += text
            await event_queue.put(AgentThinkingChunk(text=text))

        async def on_text(text: str) -> None:
            nonlocal thinking_complete
            if not text:
                return
            if saw_thinking and not thinking_complete:
                await event_queue.put(AgentThinkingComplete(full_text=full_thinking))
                thinking_complete = True
            await event_queue.put(AgentStreamChunk(text=text))

        try:
            from cli_textual.agents.observability import trace_context
            from pydantic_ai import AgentRunResultEvent
            from pydantic_ai.messages import (
                PartDeltaEvent,
                PartStartEvent,
                TextPartDelta,
                ThinkingPartDelta,
            )
            from pydantic_ai.usage import UsageLimits

            final_result = None
            with trace_context(prompt, session_id):
                async for ev in agent.run_stream_events(
                    prompt, deps=deps, message_history=message_history,
                    usage_limits=UsageLimits(request_limit=request_limit),
                ):
                    if isinstance(ev, PartStartEvent):
                        part = ev.part
                        if isinstance(part, ThinkingPart):
                            await on_thinking(part.content)
                        elif isinstance(part, TextPart):
                            await on_text(part.content)
                    elif isinstance(ev, PartDeltaEvent):
                        delta = ev.delta
                        if isinstance(delta, ThinkingPartDelta):
                            await on_thinking(delta.content_delta or "")
                        elif isinstance(delta, TextPartDelta):
                            await on_text(delta.content_delta or "")
                    elif isinstance(ev, AgentRunResultEvent):
                        final_result = ev.result

            # Thinking with no following text still needs a completion marker.
            if saw_thinking and not thinking_complete:
                await event_queue.put(AgentThinkingComplete(full_text=full_thinking))

            new_history = final_result.new_messages() if final_result else None
            await event_queue.put(AgentComplete(new_history=new_history))
        except Exception as e:
            await event_queue.put(AgentStreamChunk(text=f"\n\n**Error:** {e}"))
            await event_queue.put(AgentComplete())

    # Run the agent in the background
    task = asyncio.create_task(run_agent())

    # Yield events to the consumer as they come in
    while True:
        event = await event_queue.get()
        yield event
        if isinstance(event, AgentComplete):
            break


# ---------------------------------------------------------------------------
# Manager Pipeline Wrapper
# ---------------------------------------------------------------------------
async def run_manager_pipeline(
    prompt: str,
    input_queue: asyncio.Queue,
    message_history: List[Any] | None = None,
    session_id: str | None = None,
    request_limit: int | None = None,
) -> AsyncGenerator[ChatEvent, None]:
    """Execute the manager orchestration using queues for UI bridging.

    Thin wrapper around :func:`run_pipeline` that drives the lazy
    manager-agent singleton. Kept for backwards compatibility.
    """
    async for event in run_pipeline(
        get_agent(),
        prompt,
        input_queue,
        message_history=message_history,
        session_id=session_id,
        request_limit=request_limit,
    ):
        yield event
