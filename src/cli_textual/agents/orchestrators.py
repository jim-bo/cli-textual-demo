import os
import asyncio
from pathlib import Path
from typing import AsyncGenerator, List, Any
import httpx
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import ModelMessage

from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentToolOutput,
    AgentStreamChunk, AgentComplete, AgentRequiresUserInput, ChatDeps, AgentExecuteCommand
)
from cli_textual.agents.specialists import model, intent_resolver, data_validator, result_generator
from cli_textual.core.agent_schemas import IntentResolution, ValidationResult, StructuredResult
from cli_textual.agents.prompt_loader import PROMPTS

from openai import AsyncOpenAI

# Configure a slightly "smarter" model for the Manager agent if available
api_key = os.getenv("OPENROUTER_API_KEY")
manager_model = TestModel()

# ---------------------------------------------------------------------------
# Procedural Orchestration
# Explicit step-by-step logic in Python
# ---------------------------------------------------------------------------
async def run_procedural_pipeline(prompt: str, message_history: List[Any] = None) -> AsyncGenerator[ChatEvent, None]:
    """Execute the pipeline step-by-step using Python flow control."""
    
    # 1. Resolve Intent
    yield AgentThinking(message="Resolving primary intent...")
    await asyncio.sleep(0.5) 
    
    # Step 1: Call Intent Resolver
    yield AgentToolStart(tool_name="intent_resolver", args={"query": prompt})
    res = await intent_resolver.run(prompt, message_history=message_history)
    intent: IntentResolution = res.output
    yield AgentToolEnd(tool_name="intent_resolver", result=f"Resolved to {intent.target_id}")
    
    # Check for clarification
    if intent.clarification_needed:
        yield AgentStreamChunk(text=f"**Clarification Required:**\n\n{intent.clarification_needed}")
        yield AgentComplete(new_history=res.new_messages())
        return

    # 2. Validate Details
    yield AgentThinking(message=f"Validating details for {intent.target_id}...")
    yield AgentToolStart(tool_name="data_validator", args={"target_id": intent.target_id})
    val_res = await data_validator.run(f"Validating for {prompt} in {intent.target_id}", message_history=res.all_messages())
    validation: ValidationResult = val_res.output
    yield AgentToolEnd(tool_name="data_validator", result="Validation complete")

    # 3. Generate Result
    yield AgentThinking(message="Constructing final structured result...")
    yield AgentToolStart(tool_name="result_generator", args={"target_id": intent.target_id, "details": validation.available_attributes})
    result_res = await result_generator.run(f"Generate result for {intent.target_id} with {validation.available_attributes}", message_history=val_res.all_messages())
    result: StructuredResult = result_res.output
    
    yield AgentStreamChunk(text=f"### Result Found!\n\n{result.explanation}\n\n**Output:** {result.output_data}")
    yield AgentComplete(new_history=result_res.new_messages())

# ---------------------------------------------------------------------------
# Manager Orchestration
# A router agent that delegates to sub-agents as tools
# ---------------------------------------------------------------------------
manager_agent = Agent(
    model,
    deps_type=ChatDeps,
    system_prompt=PROMPTS['orchestrators']['manager']['system_prompt']
)

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
async def execute_slash_command(ctx: RunContext[ChatDeps], command_name: str, args: List[str] = None) -> str:
    """Execute a TUI slash command (e.g. '/clear', '/ls'). 
    Use this to trigger UI actions or system tools.
    """
    if args is None: args = []
    # Ensure command name starts with /
    if not command_name.startswith("/"):
        command_name = f"/{command_name}"
    await ctx.deps.event_queue.put(AgentExecuteCommand(command_name=command_name, args=args))
    return f"Command {command_name} triggered in UI."

@manager_agent.tool
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
    MAX_OUTPUT = 8192
    output_parts: list[str] = []
    exit_code = 1
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=working_dir,
        )
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(1024)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            output_parts.append(text)
            await ctx.deps.event_queue.put(AgentToolOutput(tool_name="bash_exec", content=text))
        await proc.wait()
        exit_code = proc.returncode or 0
    except Exception as exc:
        err = f"Error: {exc}"
        await ctx.deps.event_queue.put(AgentToolOutput(tool_name="bash_exec", content=err, is_error=True))
        await ctx.deps.event_queue.put(AgentToolEnd(tool_name="bash_exec", result="error"))
        return err

    full_output = "".join(output_parts)
    truncated = ""
    if len(full_output) > MAX_OUTPUT:
        full_output = full_output[:MAX_OUTPUT]
        truncated = "\n[output truncated]"
    result = f"Exit code: {exit_code}\n{full_output}{truncated}"
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="bash_exec", result=f"exit {exit_code}"))
    return result


@manager_agent.tool
async def read_file(ctx: RunContext[ChatDeps], path: str, start_line: int = 1, end_line: int = None) -> str:
    """Read the contents of a local file, optionally restricted to a line range.

    Args:
        path: File path (relative to CWD or absolute)
        start_line: First line to include, 1-indexed (default: 1)
        end_line: Last line to include (default: read all, capped at 200 lines)
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="read_file", args={"path": path}))
    MAX_CHARS = 8192
    MAX_LINES = 200
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line if end_line is not None else len(lines))
        end = min(end, start + MAX_LINES)
        selected = lines[start:end]
        content = "\n".join(selected)
        truncated = ""
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
            truncated = "\n[truncated]"
        result = content + truncated
    except Exception as exc:
        result = f"Error reading file: {exc}"
        await ctx.deps.event_queue.put(AgentToolOutput(tool_name="read_file", content=result, is_error=True))
        await ctx.deps.event_queue.put(AgentToolEnd(tool_name="read_file", result="error"))
        return result

    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="read_file", content=result))
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="read_file", result=f"{len(selected)} lines"))
    return result


@manager_agent.tool
async def web_fetch(ctx: RunContext[ChatDeps], url: str) -> str:
    """Fetch the contents of a URL via HTTP GET and return the response body.

    Use this for REST APIs, documentation pages, or any web resource.
    Response body is capped at 8 KB; a truncation note is appended when exceeded.

    Args:
        url: The URL to fetch
    """
    await ctx.deps.event_queue.put(AgentToolStart(tool_name="web_fetch", args={"url": url}))
    MAX_CHARS = 8192
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            response = await client.get(url)
        body = response.text
        truncated = ""
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = "\n[truncated]"
        result = f"HTTP {response.status_code}\n{body}{truncated}"
    except Exception as exc:
        result = f"Error fetching URL: {exc}"
        await ctx.deps.event_queue.put(AgentToolOutput(tool_name="web_fetch", content=result, is_error=True))
        await ctx.deps.event_queue.put(AgentToolEnd(tool_name="web_fetch", result="error"))
        return result

    await ctx.deps.event_queue.put(AgentToolOutput(tool_name="web_fetch", content=result))
    await ctx.deps.event_queue.put(AgentToolEnd(tool_name="web_fetch", result=f"HTTP {response.status_code}"))
    return result


@manager_agent.tool
async def call_intent_resolver(ctx: RunContext[ChatDeps], query: str) -> str:
    """Resolve a user's natural language query to a specific target identifier."""
    res = await intent_resolver.run(query)
    data: IntentResolution = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    return f"RESOLVED: {data.target_id} ({data.target_name}) - Confidence: {data.confidence}"

@manager_agent.tool
async def call_data_validator(ctx: RunContext[ChatDeps], target_id: str, question: str) -> str:
    """Validate if the target contains the details required by the user's question."""
    res = await data_validator.run(f"Check {target_id} for {question}")
    data: ValidationResult = res.output
    if data.clarification_needed:
        return f"CLARIFICATION REQUIRED: {data.clarification_needed}"
    status = "VALID" if data.is_valid else "PARTIAL"
    return f"STATUS: {status} - Details: {data.available_attributes}"

@manager_agent.tool
async def call_result_generator(ctx: RunContext[ChatDeps], target_id: str, details: List[str], question: str) -> str:
    """Generate the final structured result."""
    res = await result_generator.run(f"Generate result for {target_id} with {details} for {question}")
    data: StructuredResult = res.output
    return f"RESULT: {data.explanation} - Data: {data.output_data}"

# ---------------------------------------------------------------------------
# Manager Pipeline Wrapper
# ---------------------------------------------------------------------------
async def run_manager_pipeline(
    prompt: str, 
    input_queue: asyncio.Queue, 
    message_history: List[Any] = None
) -> AsyncGenerator[ChatEvent, None]:
    """Execute the manager orchestration using queues for UI bridging."""
    event_queue = asyncio.Queue()
    deps = ChatDeps(event_queue=event_queue, input_queue=input_queue)
    
    await event_queue.put(AgentThinking(message="Manager orchestrator initializing..."))
    
    async def run_agent():
        try:
            async with manager_agent.run_stream(prompt, deps=deps, message_history=message_history) as result:
                last_length = 0
                async for text in result.stream_text():
                    new_part = text[last_length:]
                    if new_part:
                        await event_queue.put(AgentStreamChunk(text=new_part))
                        last_length = len(text)

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
