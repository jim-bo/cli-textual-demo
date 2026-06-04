"""Tests for the shared pricing/context helpers in ``agents/pricing.py``."""

from dataclasses import dataclass

import pytest

from cli_textual.agents.pricing import (
    DEFAULT_CONTEXT,
    MODEL_CONTEXT,
    PRICES,
    context_left_pct,
    estimate_cost,
)

pytestmark = pytest.mark.timeout(5)


@dataclass
class _Usage:
    """Minimal stand-in for a pydantic-ai usage object."""

    input_tokens: int = 0
    output_tokens: int = 0


def test_estimate_cost_known_model():
    model = "anthropic/claude-sonnet-4.6"
    pin, pout = PRICES[model]
    usage = _Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert estimate_cost(model, usage) == pytest.approx(pin + pout)


def test_estimate_cost_unknown_model_is_zero():
    usage = _Usage(input_tokens=5000, output_tokens=5000)
    assert estimate_cost("totally/unknown-model", usage) == 0.0


def test_estimate_cost_accepts_request_response_token_aliases():
    """Some usage objects expose request_tokens/response_tokens instead."""

    @dataclass
    class _AliasUsage:
        request_tokens: int = 0
        response_tokens: int = 0

    model = "qwen/qwen3-coder"
    pin, pout = PRICES[model]
    usage = _AliasUsage(request_tokens=2_000_000, response_tokens=1_000_000)
    assert estimate_cost(model, usage) == pytest.approx(2 * pin + pout)


def test_context_left_pct_half_full():
    model = next(iter(MODEL_CONTEXT))
    window = MODEL_CONTEXT[model]
    assert context_left_pct(model, window // 2) == pytest.approx(50.0, rel=0.01)


def test_context_left_pct_clamps_to_zero_when_over():
    model = next(iter(MODEL_CONTEXT))
    window = MODEL_CONTEXT[model]
    assert context_left_pct(model, window * 2) == 0.0


def test_context_left_pct_unknown_model_uses_default():
    # Empty context → 100% left, computed against DEFAULT_CONTEXT.
    assert context_left_pct("totally/unknown-model", 0) == pytest.approx(100.0)
    half = context_left_pct("totally/unknown-model", DEFAULT_CONTEXT // 2)
    assert half == pytest.approx(50.0, rel=0.01)
