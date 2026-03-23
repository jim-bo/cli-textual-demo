# Architecture Refactor: Teaching Package

## Goal

Reorganize the codebase so each concept is self-evident to a reader:

- **Tools** (`tools/`) — pure async functions, zero TUI dependency
- **Agents** (`agents/`) — LLM orchestration that wraps tools and emits events
- **Events** (`core/chat_events.py`) — typed contract between agents and TUI
- **TUI** (`app.py`, `plugins/`, `ui/`) — subscribes to events, renders them

## Progress Tracker

| Phase | Description | Status |
|-------|------------|--------|
| 1 | Extract pure tools into `tools/` module | **done** |
| 2 | Remove specialists, procedural pipeline, dummy agent; extract model config | **done** |
| 3 | Rename orchestrators → manager, add architecture boundary tests | pending |

## Phase Details

### Phase 1: Extract pure tools into `tools/` module

Tools become TUI-independent pure functions returning `ToolResult`. Orchestrator `@tool` wrappers delegate to pure functions and handle event emission.

**Create**: `tools/__init__.py`, `tools/base.py`, `tools/bash.py`, `tools/read_file.py`, `tools/web_fetch.py`, `tests/unit/test_pure_tools.py`
**Modify**: `agents/orchestrators.py` (wrappers delegate to pure functions)

### Phase 2: Remove dead weight, extract model config

Delete specialists, procedural pipeline, dummy agent, agent schemas. Move `get_model()` to `agents/model.py`.

**Create**: `agents/model.py`
**Delete**: `agents/specialists.py`, `core/agent_schemas.py`, `core/dummy_agent.py`
**Modify**: `agents/orchestrators.py`, `app.py`, `agents/prompts.yaml`, `plugins/commands/mode.py`, tests

### Phase 3: Rename orchestrators → manager, architecture boundary tests

Final structure. Rename for clarity. Architecture tests prove tools have no TUI imports.

**Create**: `agents/__init__.py`, `tests/unit/test_architecture.py`
**Rename**: `agents/orchestrators.py` → `agents/manager.py`
**Modify**: All files importing from `agents.orchestrators`

## Target Structure

```
src/cli_textual/
  tools/                    # Pure functions, ZERO TUI dependency
    base.py                 # ToolResult dataclass
    bash.py                 # bash_exec() -> ToolResult
    read_file.py            # read_file() -> ToolResult
    web_fetch.py            # web_fetch() -> ToolResult
  agents/                   # LLM orchestration
    __init__.py             # re-exports
    model.py                # get_model() + model instance
    manager.py              # manager_agent + @tool wrappers + run_manager_pipeline
    prompts.yaml
    prompt_loader.py
  core/                     # Framework utilities
    chat_events.py          # Event dataclasses
    command.py              # SlashCommand + CommandManager
    fs.py, permissions.py
  plugins/commands/         # Slash commands (TUI-only)
  ui/                       # Widgets + screens
  app.py                    # Main TUI app
```
