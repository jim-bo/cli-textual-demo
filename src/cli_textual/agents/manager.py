import asyncio
import os
from typing import AsyncGenerator, List, Any
from pydantic_ai import Agent, RunContext

from pydantic_ai.messages import ThinkingPart, TextPart

from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentToolOutput,
    AgentStreamChunk, AgentComplete, AgentRequiresUserInput, ChatDeps, AgentExecuteCommand,
    AgentThinkingChunk, AgentThinkingComplete,
)
from pathlib import Path
from cli_textual.agents.model import model
from cli_textual.tools.bash import bash_exec as pure_bash_exec
from cli_textual.tools.read_file import read_file as pure_read_file
from cli_textual.tools.web_fetch import web_fetch as pure_web_fetch
from cli_textual.agents.prompt_loader import PROMPTS

# ---------------------------------------------------------------------------
# Safe Mode
# ---------------------------------------------------------------------------
SAFE_MODE = os.getenv("SAFE_MODE", "").lower() in ("1", "true", "yes")


def _get_system_prompt() -> str:
    base = PROMPTS['orchestrators']['manager']['system_prompt']
    if SAFE_MODE:
        base += "\n\n" + PROMPTS['orchestrators']['manager']['safety_preamble']
    return base


# ---------------------------------------------------------------------------
# Manager Orchestration
# A router agent that delegates to sub-agents as tools
# ---------------------------------------------------------------------------
manager_agent = Agent(
    model,
    deps_type=ChatDeps,
    system_prompt=_get_system_prompt(),
)


# ---------------------------------------------------------------------------
# Tool wrappers (module-level for testability)
# ---------------------------------------------------------------------------

@manager_agent.tool
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


@manager_agent.tool
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


@manager_agent.tool
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


@manager_agent.tool
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


# Register bash_exec only when not in safe mode
if not SAFE_MODE:
    manager_agent.tool(bash_exec)


# ---------------------------------------------------------------------------
# Manager Pipeline Wrapper
# ---------------------------------------------------------------------------
async def run_manager_pipeline(
    prompt: str,
    input_queue: asyncio.Queue,
    message_history: List[Any] | None = None
) -> AsyncGenerator[ChatEvent, None]:
    """Execute the manager orchestration using queues for UI bridging."""
    event_queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)

    await event_queue.put(AgentThinking(message="Manager orchestrator initializing..."))

    async def run_agent():
        try:
            async with manager_agent.run_stream(prompt, deps=deps, message_history=message_history) as result:
                last_thinking_len = 0
                last_text_len = 0
                thinking_complete = False
                full_thinking = ""

                async for response, is_last in result.stream_responses():
                    # Accumulate thinking and text from all parts
                    thinking_text = ""
                    text_text = ""
                    for part in response.parts:
                        if isinstance(part, ThinkingPart):
                            thinking_text += part.content
                        elif isinstance(part, TextPart):
                            text_text += part.content

                    # Emit thinking deltas
                    if len(thinking_text) > last_thinking_len:
                        new_thinking = thinking_text[last_thinking_len:]
                        await event_queue.put(AgentThinkingChunk(text=new_thinking))
                        last_thinking_len = len(thinking_text)
                        full_thinking = thinking_text

                    # Signal thinking done when text starts
                    if text_text and not thinking_complete and last_thinking_len > 0:
                        await event_queue.put(AgentThinkingComplete(full_text=full_thinking))
                        thinking_complete = True

                    # Emit text deltas
                    if len(text_text) > last_text_len:
                        new_text = text_text[last_text_len:]
                        await event_queue.put(AgentStreamChunk(text=new_text))
                        last_text_len = len(text_text)

                # If thinking was emitted but no text followed, still signal complete
                if last_thinking_len > 0 and not thinking_complete:
                    await event_queue.put(AgentThinkingComplete(full_text=full_thinking))

                await event_queue.put(AgentComplete(new_history=result.new_messages()))
        except Exception as e:
            await event_queue.put(AgentStreamChunk(text=f"\n\n**Error:** {e}"))
            await event_queue.put(AgentComplete())

    # Run the agent in the background
    task = asyncio.create_task(run_agent())

    # Yield events to the TUI as they come in
    while True:
        event = await event_queue.get()
        yield event
        if isinstance(event, AgentComplete):
            break
