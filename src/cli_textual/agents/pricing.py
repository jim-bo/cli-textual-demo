"""Model pricing + context-window helpers, shared by the TUI status bar and
the bench harness.

Single source of truth for the per-model price table and cost math (previously
duplicated in ``bench/mcp/run_mcp_smoke.py``). Pure functions, no TUI imports.
"""

from typing import Any

# Per-1M-token (input, output) USD prices for cost estimation. Extend as needed.
PRICES: dict[str, tuple[float, float]] = {
    "qwen/qwen3-coder": (0.22, 1.80),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
}

# Max context window (tokens) per model, for the status-bar "context left %"
# surface. Unknown models fall back to ``DEFAULT_CONTEXT``.
DEFAULT_CONTEXT = 128_000
MODEL_CONTEXT: dict[str, int] = {
    "qwen/qwen3-coder": 262_144,
    "anthropic/claude-sonnet-4.6": 200_000,
}


def _tokens(usage: Any, *names: str) -> int:
    """First non-zero attribute among ``names`` on a usage object, else 0."""
    for name in names:
        val = getattr(usage, name, None)
        if val:
            return val
    return 0


def token_counts(usage: Any) -> tuple[int, int]:
    """``(input_tokens, output_tokens)`` from a usage object.

    Handles both pydantic-ai naming conventions: ``input_tokens``/``output_tokens``
    and the older ``request_tokens``/``response_tokens``.
    """
    return (
        _tokens(usage, "input_tokens", "request_tokens"),
        _tokens(usage, "output_tokens", "response_tokens"),
    )


def estimate_cost(model: str, usage: Any) -> float:
    """USD cost of a run, from its usage object and the price table.

    Unknown models cost 0.
    """
    inp, out = token_counts(usage)
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (inp * pin + out * pout) / 1_000_000


def context_left_pct(model: str, input_tokens: int) -> float:
    """Percent of the model's context window still free, clamped to [0, 100].

    ``input_tokens`` is used as a proxy for the current context size (the most
    recent request carries the full prompt+history). See the call site in
    ``app.py`` for the over-count caveat on tool-heavy turns.
    """
    window = MODEL_CONTEXT.get(model, DEFAULT_CONTEXT)
    if window <= 0:
        return 0.0
    return max(0.0, (window - input_tokens) / window * 100.0)
