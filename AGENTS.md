# AGENTS.md

Teaching package: building AI agent TUIs with Textual + pydantic-ai. Each layer is independent and testable.

## Setup

```bash
uv sync
uv run demo-cli          # terminal
uv run pytest tests/unit/ -v  # tests (5s timeout per test)
```

## Architecture

```
tools/   → pure async functions returning ToolResult (no TUI imports)
core/    → chat_events.py defines typed events (agent↔TUI contract)
agents/  → pydantic-ai agent wraps tools, emits events via queue
app.py   → Textual TUI consumes events, renders UI
plugins/ → slash commands (auto-discovered)
```

Dependencies flow down only: TUI → agents → events ← tools

## Testing

- TDD required. Write failing test first, then implement.
- Use `FunctionModel(stream_function=...)` for deterministic agent tests. Never use `TestModel` (it generates random tool calls).
- TUI tests: `async with app.run_test() as pilot` — always `await pilot.pause()` after simulated actions.
- 5-second per-test timeout enforced via pytest-timeout.

## Textual Gotchas

- `widget.remove()` is async — await it before mounting a replacement with the same ID.
- Use `self.call_after_refresh(widget.focus)` to focus newly mounted widgets.
- Normalize key strings with `.lower()` — capitalization varies by terminal.
- Never use `COMMANDS` as a class variable name — reserved by Textual's Command Palette.
- In tests, `await pilot.pause(0.1)` after key presses before asserting UI state.

## Git Workflow

- Never commit directly to main. Always create a feature branch.
- Commit logical chunks with descriptive messages.
- Push the branch and create a PR via `gh pr create`.
- Wait for CodeRabbit review. Read its comments, fix valid findings, reply to each.
- Once all findings are addressed and tests pass, merge via `gh pr merge`.
- Sensitive files (`.gemini/`, `.claude/`, `.agents/`) are gitignored — never commit API keys.

## Maintaining AGENTS.md

Every directory has its own AGENTS.md describing that level only. CLAUDE.md and GEMINI.md are symlinks to AGENTS.md.

**Rule**: when you modify a directory, check if the change affects how an agent should navigate or work there. If so, update that directory's AGENTS.md. Keep entries concise — these are for machines, not humans.
