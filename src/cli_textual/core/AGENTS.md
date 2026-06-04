# AGENTS.md — core/

Framework utilities shared across agents and TUI.

## Files

- `chat_events.py` — typed event dataclasses (`ChatEvent` subclasses). This is the agent↔TUI contract. Events: `AgentThinking`, `AgentThinkingChunk`, `AgentThinkingComplete`, `AgentToolStart`, `AgentToolEnd`, `AgentToolOutput`, `AgentStreamChunk`, `AgentComplete`, `AgentRequiresUserInput`, `AgentExecuteCommand`. Also defines `ChatDeps`. `AgentComplete` carries `new_history` and the run `usage` (token counts, used by the status-bar cost/context surface).
- `command.py` — `SlashCommand` base class + `CommandManager` with `auto_discover()` for plugin loading.
- `formatting.py` — pure display helpers for tool-call args: `format_args_inline` (opencode-style `name(args)` summary for collapsible titles) and `format_args_block` (pretty JSON for the expanded body). No TUI imports.
- `fs.py` — `FSManager` for path-jailed filesystem operations.
- `permissions.py` — `PermissionManager` reads/writes tool approvals to `.agents/settings.json`.
