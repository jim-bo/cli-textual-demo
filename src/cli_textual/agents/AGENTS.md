# AGENTS.md — agents/

## Files

- `manager.py` — `manager_agent` (pydantic-ai Agent) + `@tool` wrappers + `run_manager_pipeline()` async generator
- `model.py` — model selection via `PYDANTIC_AI_MODEL` and `OPENROUTER_API_KEY` env vars
- `prompts.yaml` — externalized system prompts loaded by `prompt_loader.py`

## Key Patterns

- Pipeline uses `stream_responses()` (not `stream_text()`) to capture both thinking and text tokens.
- Tool wrappers delegate to pure functions in `tools/` and emit events to `event_queue`.
- `ChatDeps` (from `core/chat_events.py`) carries `event_queue` and `input_queue` as agent dependencies.
- To add a new tool: write the pure function in `tools/`, then add a `@manager_agent.tool` wrapper here that emits `AgentToolStart` → delegates → `AgentToolOutput` → `AgentToolEnd`.
- **Safe mode** (`SAFE_MODE=1` env var): disables `bash_exec` tool and appends `safety_preamble` from `prompts.yaml` to the system prompt. Set in Dockerfile for public hosting.
