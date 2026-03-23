# Agent TUI — A Teaching Package for Building AI Agent Interfaces

A Python reference implementation showing how to build a terminal-based AI agent with tool use, interactive UI, and streaming responses. Built with [Textual](https://textual.textualize.io/) and [pydantic-ai](https://ai.pydantic.dev/).

## Why This Exists

Modern AI coding assistants (Claude Code, opencode, aider) blend LLM orchestration with terminal UIs, but their codebases are large and hard to learn from. This project isolates the core patterns into a small, readable package where each concept lives in its own layer:

- **Tools** — pure async functions with zero UI dependency
- **Agents** — LLM orchestration that wraps tools and emits events
- **Events** — typed contract between agents and the TUI
- **TUI** — subscribes to events, renders them

## Features

### Agent Capabilities
- **Streaming responses** — text streams token-by-token into a live Markdown widget
- **Thinking transparency** — reasoning tokens from thinking models (Claude, etc.) render in collapsible panels
- **Tool use** — the agent can run shell commands, read files, and fetch URLs
- **Interactive selection** — the agent can present options and wait for the user's choice
- **Multi-turn conversation** — message history preserves context across turns
- **Slash commands** — extensible command system with auto-discovery and autocomplete

### Slash Commands
| Command | Description |
|---------|-------------|
| `/help` | List available commands |
| `/clear` | Clear conversation history |
| `/mode` | Set agent orchestration mode |
| `/tools` | Browse available agent tools with descriptions |
| `/verbose` | Toggle thinking/reasoning visibility |
| `/ls` | Directory listing (path-jailed for security) |
| `/head` | View file contents |
| `/load` | Simulated background task with spinner |
| `/select` | Interactive selection menu |
| `/survey` | Multi-tab interactive survey |

### TUI Features
- Growing multi-line input area with shift+enter for newlines
- Autocomplete for slash commands
- Permission system with approval modal
- Double ctrl+d to exit
- DNA helix spinner during agent processing

## Architecture

```
src/cli_textual/
  tools/                    # Pure functions, ZERO TUI dependency
    base.py                 # ToolResult dataclass
    bash.py                 # bash_exec() -> ToolResult
    read_file.py            # read_file() -> ToolResult
    web_fetch.py            # web_fetch() -> ToolResult
  agents/                   # LLM orchestration
    manager.py              # manager_agent + @tool wrappers + run_manager_pipeline
    model.py                # Model selection (OpenRouter, Anthropic, Gemini, OpenAI)
    prompts.yaml            # System prompts (externalized)
    prompt_loader.py        # YAML loader
  core/                     # Framework utilities
    chat_events.py          # Event dataclasses (the agent↔TUI contract)
    command.py              # SlashCommand base class + CommandManager
    fs.py                   # FSManager (path jailing)
    permissions.py          # Tool approval persistence
  plugins/commands/         # Slash commands (auto-discovered)
  ui/widgets/               # Custom Textual widgets
  ui/screens/               # Modal screens
  app.py                    # Main TUI application
```

### Event Flow

The agent and TUI communicate through a typed event stream:

```
User input → run_manager_pipeline() → Agent (pydantic-ai)
                                         ↓
                                    event_queue
                                         ↓
              stream_agent_response() ← ChatEvent
                    ↓
         TUI renders: spinners, tool output, thinking, markdown
```

Key events: `AgentThinking`, `AgentThinkingChunk`, `AgentToolStart`, `AgentToolOutput`, `AgentToolEnd`, `AgentStreamChunk`, `AgentComplete`

### Tool Architecture

Tools are pure async functions that return `ToolResult` — no TUI imports, no queues, no events. The agent's `@tool` wrappers delegate to pure functions and handle event emission:

```python
# Pure tool (tools/bash.py) — usable anywhere
async def bash_exec(command: str) -> ToolResult:
    ...

# Agent wrapper (agents/manager.py) — emits events for TUI
@manager_agent.tool
async def bash_exec(ctx, command: str) -> str:
    await ctx.deps.event_queue.put(AgentToolStart(...))
    result = await pure_bash_exec(command)
    await ctx.deps.event_queue.put(AgentToolOutput(...))
    return result.output
```

This separation is enforced by architecture boundary tests that scan `tools/` for prohibited imports.

## Getting Started

### Prerequisites
- Python 3.10+
- [uv](https://github.com/astral-sh/uv)

### Installation
```bash
git clone <repo-url>
cd cbio-cli-textual
uv sync
```

### Configuration

Set your model via environment variables:

```bash
# OpenRouter (default — any model, free or paid)
export OPENROUTER_API_KEY="sk-or-..."
export PYDANTIC_AI_MODEL="nvidia/nemotron-3-super-120b-a12b:free"

# Or use a native provider directly
export PYDANTIC_AI_MODEL="anthropic:claude-sonnet-4-20250514"
export PYDANTIC_AI_MODEL="gemini:gemini-2.0-flash"
export PYDANTIC_AI_MODEL="openai:gpt-4o"

# For testing without an API key
export PYDANTIC_AI_MODEL="test"
```

### Running

```bash
# Terminal
uv run demo-cli

# Browser (via textual-serve)
PYTHONPATH=src uv run textual serve src/cli_textual/app.py

# Docker
docker build -t agent-tui .
docker run -p 7860:7860 -e OPENROUTER_API_KEY="..." agent-tui
```

## Testing

61 unit tests with a 5-second per-test timeout. Tests use pydantic-ai's `FunctionModel` for deterministic, API-free agent testing.

```bash
uv run pytest tests/unit/ -v
```

Test categories:
- **Architecture** — boundary tests proving `tools/` has no TUI imports
- **Pipeline** — event emission, thinking tokens, multi-turn history
- **TUI** — widget rendering, commands, interactions via `textual.pilot`
- **Pure tools** — bash, file read, web fetch without any agent context

## License

MIT
