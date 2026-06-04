#!/usr/bin/env python3
"""Lightweight MCP smoke-benchmark.

Attaches the fixed local MCP server (``server.py``) to a real cli-textual agent
and runs a handful of scripted tasks that each *require* an MCP tool. Scores each
task on two axes — did the agent call the expected tool, and did its final answer
contain the expected result — and reports per-task latency plus total token cost.

This validates the MCP integration end-to-end on a real model and answers a
practical question cheaply: *can a budget model reliably drive MCP tools?* It is
deliberately tiny; the heavyweight public suites (MCP-Bench, MCP-AgentBench,
MCPToolBench++) are noted in FINDINGS as future reference.

Usage (from the cli-textual repo root, after loading the shared key):
    set -a; . ../.env; set +a
    PYDANTIC_AI_MODEL=qwen/qwen3-coder python bench/mcp/run_mcp_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.messages import ToolCallPart

# Make the cli-textual package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cli_textual.agents.manager import build_agent  # noqa: E402
from cli_textual.agents.mcp import _emit_events, set_mcp_servers  # noqa: E402

SERVER = Path(__file__).with_name("server.py")

# Per-1M-token (input, output) USD prices for cost estimation. Extend as needed.
PRICES = {
    "qwen/qwen3-coder": (0.22, 1.80),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
}


@dataclass
class Task:
    prompt: str
    tool: str          # expected MCP tool name
    expect: str        # case-insensitive substring expected in the final answer


TASKS = [
    Task("Add 17 and 25 using a tool. Reply with just the number.", "add", "42"),
    Task("Multiply 6 and 7 using a tool. Reply with just the number.", "multiply", "42"),
    Task("Reverse the text 'hello world' using a tool. Reply with just the result.",
         "reverse_text", "dlrow olleh"),
    Task("Count the words in 'the quick brown fox jumps' using a tool. Reply with the number.",
         "count_words", "5"),
    Task("There is a tool that returns a secret word. Call it and tell me the word.",
         "secret_word", "marmoset"),
]


def _cost(model: str, usage) -> float:
    inp = getattr(usage, "input_tokens", None) or getattr(usage, "request_tokens", 0) or 0
    out = getattr(usage, "output_tokens", None) or getattr(usage, "response_tokens", 0) or 0
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (inp * pin + out * pout) / 1_000_000


def _tools_called(messages) -> list[str]:
    return [
        p.tool_name
        for m in messages
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


async def main() -> int:
    model = os.getenv("PYDANTIC_AI_MODEL", "qwen/qwen3-coder")
    server = MCPServerStdio(
        command=sys.executable, args=[str(SERVER)],
        id="smoke", tool_prefix=None, process_tool_call=_emit_events,
    )
    set_mcp_servers([server])
    agent = build_agent()

    print(f"MCP smoke-bench — model={model}\n")
    header = f"{'task':<14}{'tool✓':<7}{'answer✓':<9}{'latency':<9}{'cost'}"
    print(header)
    print("-" * len(header))

    passed = 0
    total_cost = 0.0
    async with agent:  # keep the MCP subprocess warm across tasks
        for t in TASKS:
            start = time.monotonic()
            task_cost = 0.0
            try:
                result = await agent.run(t.prompt, deps=None)
                answer = result.output or ""
                called = _tools_called(result.all_messages())
                task_cost = _cost(model, result.usage())
            except Exception as exc:  # noqa: BLE001
                answer, called = f"<error: {exc}>", []
            dur = time.monotonic() - start
            total_cost += task_cost

            tool_ok = t.tool in called
            ans_ok = t.expect.lower() in answer.lower()
            if tool_ok and ans_ok:
                passed += 1
            tick = lambda ok: "✓" if ok else "✗"  # noqa: E731
            print(f"{t.tool:<14}{tick(tool_ok):<7}{tick(ans_ok):<9}{dur:>6.1f}s  ${task_cost:.4f}")

    print("-" * len(header))
    print(f"\n{passed}/{len(TASKS)} tasks passed   total cost ${total_cost:.4f}")
    return 0 if passed == len(TASKS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
