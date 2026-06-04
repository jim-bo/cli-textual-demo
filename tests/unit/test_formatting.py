"""Tests for the tool-arg display helpers in ``core/formatting.py``."""

import json

import pytest

from cli_textual.core.formatting import format_args_block, format_args_inline

pytestmark = pytest.mark.timeout(5)


def test_format_args_inline_empty_and_none():
    assert format_args_inline({}) == ""
    assert format_args_inline(None) == ""


def test_format_args_inline_single_and_multi():
    assert format_args_inline({"path": "a.txt"}) == "path='a.txt'"
    out = format_args_inline({"a": 1, "b": True})
    assert out == "a=1, b=True"


def test_format_args_inline_truncates_long_string_values():
    long = "x" * 200
    out = format_args_inline({"command": long})
    # Individual long values get an ellipsis and the whole line stays bounded.
    assert "…" in out
    assert len(out) <= 65


def test_format_args_inline_truncates_overall_line():
    args = {f"k{i}": "value" for i in range(40)}
    out = format_args_inline(args)
    assert len(out) <= 65
    assert out.endswith("…")


def test_format_args_block_empty_is_none():
    assert format_args_block({}) is None
    assert format_args_block(None) is None


def test_format_args_block_pretty_json():
    block = format_args_block({"path": "a.txt", "count": 3})
    assert block is not None
    # Round-trips as JSON and is indented (multi-line for >1 key).
    assert json.loads(block) == {"path": "a.txt", "count": 3}
    assert "\n" in block


def test_format_args_block_handles_non_serializable():
    class Weird:
        def __repr__(self):
            return "<weird>"

    block = format_args_block({"obj": Weird()})
    assert block is not None
    # Falls back to repr via _safe_serialize rather than raising.
    assert "<weird>" in block
