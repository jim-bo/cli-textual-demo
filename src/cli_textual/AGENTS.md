# AGENTS.md — src/cli_textual/

Entry point: `app.py` → `ChatApp`. Styling: `app.tcss`.

## Package Layout

- `agents/` — LLM orchestration (manager agent, model config, prompts)
- `tools/` — pure async tool functions (no TUI imports)
- `core/` — framework utilities (events, commands, filesystem, permissions)
- `plugins/commands/` — slash commands (auto-discovered)
- `ui/` — custom Textual widgets and modal screens
