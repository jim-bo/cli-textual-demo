# AGENTS.md — tools/

Pure async functions returning `ToolResult(output, is_error, exit_code)`. **ZERO TUI/event/queue imports.**

## Files

- `base.py` — `ToolResult` dataclass
- `bash.py` — `bash_exec(command, working_dir) -> ToolResult`
- `read_file.py` — `read_file(path, start_line, end_line) -> ToolResult`
- `web_fetch.py` — `web_fetch(url) -> ToolResult`

## Rules

- No imports from `core/chat_events.py` or `asyncio.Queue`. Enforced by `tests/unit/test_architecture.py`.
- New tools go here as pure functions. Wrap them in `agents/manager.py` for event emission.
- Tools are independently testable: `from cli_textual.tools import bash_exec; asyncio.run(bash_exec("echo hi"))`
