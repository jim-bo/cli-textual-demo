# AGENTS.md — tests/

## Layout

- `unit/` — 76 tests, 5s timeout per test. No API keys needed.
- `integration/` — requires `OPENROUTER_API_KEY`. Tests real LLM tool use end-to-end.

## Patterns

- Agent pipeline tests: use `FunctionModel(stream_function=...)` for deterministic responses. Never `TestModel`.
- Thinking tests: yield `DeltaThinkingPart(content=...)` from stream function to simulate reasoning tokens.
- Tool-call tests (streaming path): yield `{0: DeltaToolCall(name=..., json_args=...)}` from the stream function (see `test_mcp.py`). `run_pipeline` drives the streaming loop, so a plain `FunctionModel(function=...)` raises "must receive a `stream_function`".
- MCP tests (`test_mcp.py`): drive a hermetic in-process FastMCP stdio server (`importorskip("mcp.server.fastmcp")`); use `build_agent()` directly (never `get_agent()`) so the manager-agent singleton other modules bind at import is left untouched.
- TUI tests: `async with app.run_test(size=(120, 40)) as pilot` — use `pilot.press()`, `pilot.pause()`, then assert.
- `conftest.py` auto-approves slash commands via `.agents/settings.json` fixture.
