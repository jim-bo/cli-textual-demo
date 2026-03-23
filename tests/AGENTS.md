# AGENTS.md — tests/

## Layout

- `unit/` — 61 tests, 5s timeout per test. No API keys needed.
- `integration/` — requires `OPENROUTER_API_KEY`. Tests real LLM tool use end-to-end.

## Patterns

- Agent pipeline tests: use `FunctionModel(stream_function=...)` for deterministic responses. Never `TestModel`.
- Thinking tests: yield `DeltaThinkingPart(content=...)` from stream function to simulate reasoning tokens.
- TUI tests: `async with app.run_test(size=(120, 40)) as pilot` — use `pilot.press()`, `pilot.pause()`, then assert.
- `conftest.py` auto-approves slash commands via `.agents/settings.json` fixture.
