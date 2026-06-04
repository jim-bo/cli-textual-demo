# AGENTS.md — bench/

In-repo benchmarks for cli-textual (separate from the model-comparison harness
at `agents-root/bench/`).

## mcp/

Lightweight MCP smoke-benchmark.

- `server.py` — a fixed hermetic FastMCP stdio server with deterministic,
  checkable tools (`add`, `multiply`, `reverse_text`, `count_words`, `secret_word`).
- `run_mcp_smoke.py` — attaches that server to a real `build_agent()` and runs ~5
  scripted tasks that each require an MCP tool; scores tool-called + answer-correct,
  reports per-task latency + token cost. Validates the MCP integration end-to-end
  on a real model.

Run (from the cli-textual repo root):
```bash
set -a; . ../.env; set +a            # load the shared OpenRouter key
PYDANTIC_AI_MODEL=qwen/qwen3-coder uv run python bench/mcp/run_mcp_smoke.py
```
