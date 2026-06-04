# AGENTS.md — agents/

## Files

- `manager.py` — `manager_agent` (pydantic-ai Agent) + `@tool` wrappers + `run_manager_pipeline()` async generator
- `model.py` — model selection via `PYDANTIC_AI_MODEL` and `OPENROUTER_API_KEY` env vars
- `mcp.py` — MCP (Model Context Protocol) client. `build_agent` attaches servers as pydantic-ai `toolsets`; each server's `process_tool_call=_emit_events` hook emits the standard `AgentToolStart/Output/End` lifecycle so MCP tools render like built-ins. `get/set/reset_mcp_servers()` mirror `tools/registry.py`. Withheld in SAFE_MODE. `load_mcp_servers` merges scopes by precedence (low→high: opt-in `discover` import from Claude/Gemini < user `~/.config/cli-textual/mcp.json` < project `./.mcp.json` < programmatic `extra`), with `$VAR` expansion. `external_entries`/`import_to_user_config` back the `/mcp import claude|gemini` command (Gemini's `httpUrl`/`url` normalized to our schema).
- `observability.py` — optional Langfuse tracing. Activates when `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` env vars are set. Calls `Agent.instrument_all()` for automatic OTel tracing.
- `prompts.yaml` — externalized system prompts loaded by `prompt_loader.py`

## Key Patterns

- Pipeline uses `stream_responses()` (not `stream_text()`) to capture both thinking and text tokens.
- Tool wrappers delegate to pure functions in `tools/` and emit events to `event_queue`.
- `ChatDeps` (from `core/chat_events.py`) carries `event_queue` and `input_queue` as agent dependencies.
- To add a new tool: write the pure function in `tools/`, add an event-emitting wrapper here (`AgentToolStart` → delegate → `AgentToolOutput` → `AgentToolEnd`), and register it by name in `_BUILTIN_TOOLS` (add to `_UNSAFE_TOOLS` too if it mutates the filesystem or shells out). `build_agent()` attaches everything in `_BUILTIN_TOOLS`.
- **Safe mode** (`SAFE_MODE=1` env var): disables the filesystem-mutating tools (`_UNSAFE_TOOLS` = `bash_exec`, `write_file`, `edit_file`) and appends `safety_preamble` from `prompts.yaml` to the system prompt. Set in Dockerfile for public hosting.
- Built-in tools live in `_BUILTIN_TOOLS`; `write_file`/`edit_file` give the agent file-authoring/editing (`edit_file` uses the forgiving matcher in `tools/_editblock.py`).
