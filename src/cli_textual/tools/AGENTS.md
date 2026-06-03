# AGENTS.md — tools/

Pure async functions returning `ToolResult(output, is_error, exit_code)`. **ZERO TUI/event/queue imports.**

## Files

- `base.py` — `ToolResult` dataclass
- `bash.py` — `bash_exec(command, working_dir) -> ToolResult`
- `read_file.py` — `read_file(path, start_line, end_line, workspace_root) -> ToolResult` — path jailed to workspace (always on)
- `web_fetch.py` — `web_fetch(url) -> ToolResult` — SSRF protection blocks private/internal IPs (always on)
- `write_file.py` — `write_file(path, content, workspace_root) -> ToolResult` — create/overwrite, path jailed. Disabled in SAFE_MODE. Exposes `_resolve_in_workspace()` (shared jailing helper).
- `edit_file.py` — `edit_file(path, old_string, new_string, replace_all, workspace_root) -> ToolResult` — exact string replace with opencode-style uniqueness (errors on no/multiple matches); forgiving matching on whitespace/`...` drift. Disabled in SAFE_MODE.
- `_editblock.py` — forgiving search/replace matcher (`replace_most_similar_chunk`) ported from Aider (Apache-2.0; see top-level `NOTICE`). Used by `edit_file`; no third-party deps.
- `grep.py` — `grep(pattern, path, ignore_case, max_results, workspace_root)` — recursive content search (regex), structured `file:line: text`, skips VCS/build dirs + binaries, early-exits at cap. Read-only, jailed, **available in SAFE_MODE**.
- `glob_tool.py` — `glob(pattern, path, max_results, workspace_root)` — file find by glob (`**` supported), newest-first. Read-only, jailed, available in SAFE_MODE.
- `todo_write.py` — `todo_write(todos)` — stateless planning checklist (model passes the full list each call). Read-only.

## Rules

- No imports from `core/chat_events.py` or `asyncio.Queue`. Enforced by `tests/unit/test_architecture.py`.
- New tools go here as pure functions. Wrap them in `agents/manager.py` for event emission.
- Tools are independently testable: `from cli_textual.tools import bash_exec; asyncio.run(bash_exec("echo hi"))`
