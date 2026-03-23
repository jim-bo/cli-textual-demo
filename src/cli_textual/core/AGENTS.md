# AGENTS.md — core/

Framework utilities shared across agents and TUI.

## Files

- `chat_events.py` — typed event dataclasses (`ChatEvent` subclasses). This is the agent↔TUI contract. Events: `AgentThinking`, `AgentThinkingChunk`, `AgentThinkingComplete`, `AgentToolStart`, `AgentToolEnd`, `AgentToolOutput`, `AgentStreamChunk`, `AgentComplete`, `AgentRequiresUserInput`, `AgentExecuteCommand`. Also defines `ChatDeps`.
- `command.py` — `SlashCommand` base class + `CommandManager` with `auto_discover()` for plugin loading.
- `fs.py` — `FSManager` for path-jailed filesystem operations.
- `permissions.py` — `PermissionManager` reads/writes tool approvals to `.agents/settings.json`.
