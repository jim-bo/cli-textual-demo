"""Display helpers for tool-call arguments.

Pure functions (no TUI imports) so they're unit-testable and reusable across
frontends. ``format_args_inline`` produces the opencode-style ``name(args)``
summary for collapsible titles; ``format_args_block`` produces the full,
pretty-printed JSON shown when a tool row is expanded.
"""

import json
from typing import Any, Optional

from cli_textual.core.conversation_log import _safe_serialize

# Bound the inline summary so a tool row title stays scannable.
_INLINE_MAX = 60
_VALUE_MAX = 40


def _short_value(value: Any) -> str:
    """Repr a single arg value, truncating long strings with an ellipsis."""
    text = repr(value)
    if len(text) > _VALUE_MAX:
        return text[: _VALUE_MAX - 1] + "…"
    return text


def format_args_inline(args: Optional[dict]) -> str:
    """One-line ``k=v, k=v`` summary of tool args, bounded in length.

    Empty/``None`` args yield ``""``. The whole line is capped at
    ``_INLINE_MAX`` chars with a trailing ellipsis when it overflows.
    """
    if not args:
        return ""
    parts = [f"{k}={_short_value(v)}" for k, v in args.items()]
    line = ", ".join(parts)
    if len(line) > _INLINE_MAX:
        return line[: _INLINE_MAX - 1] + "…"
    return line


def format_args_block(args: Optional[dict]) -> Optional[str]:
    """Pretty-printed JSON of tool args for the expanded tool row.

    Returns ``None`` for empty/``None`` args (nothing to show). Non-JSON-native
    values are coerced via ``_safe_serialize`` (falling back to ``repr``) so this
    never raises on arbitrary tool payloads.
    """
    if not args:
        return None
    return json.dumps(_safe_serialize(args), indent=2)
