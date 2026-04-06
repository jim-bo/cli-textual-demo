"""Registry for user-provided tools.

Third-party code can call ``register_tool(fn)`` before the manager agent is
built; ``agents/manager.py`` drains this registry at build time and wraps each
pure function so it emits the standard AgentToolStart/Output/End lifecycle.

No TUI or event-queue imports live here — see ``tests/unit/test_architecture.py``.
"""
from typing import Awaitable, Callable, List

from cli_textual.tools.base import ToolResult

ToolFn = Callable[..., Awaitable[ToolResult]]

_extra_tools: List[ToolFn] = []


def register_tool(fn: ToolFn) -> ToolFn:
    """Register a pure async tool function.

    Must be called before the manager agent is constructed (i.e. before the
    first ``get_agent()`` call or ``ChatApp.run()``). The function is returned
    unchanged so this can be used as a decorator.
    """
    _extra_tools.append(fn)
    return fn


def get_extra_tools() -> List[ToolFn]:
    """Return a copy of currently registered extra tools."""
    return list(_extra_tools)


def clear_extra_tools() -> None:
    """Reset the registry. Intended for tests."""
    _extra_tools.clear()
