"""Registry for user-provided tools.

Third-party code can call ``register_tool(fn)`` before the manager agent is
built; ``agents/manager.py`` drains this registry at build time and wraps each
pure function so it emits the standard AgentToolStart/Output/End lifecycle.

The registry is keyed by ``fn.__name__`` so repeated registrations (e.g. two
``ChatApp`` instances sharing the same decorator module) are idempotent and
never collide during agent construction.

No TUI or event-queue imports live here — see ``tests/unit/test_architecture.py``.
"""
import inspect
from typing import Awaitable, Callable, Dict, List

from cli_textual.tools.base import ToolResult

ToolFn = Callable[..., Awaitable[ToolResult]]

_extra_tools: Dict[str, ToolFn] = {}


def register_tool(fn: ToolFn) -> ToolFn:
    """Register a pure async tool function.

    Must be called before the manager agent is constructed (i.e. before the
    first ``get_agent()`` call or ``ChatApp.run()``). The function is returned
    unchanged so this can be used as a decorator.

    Raises:
        TypeError: if ``fn`` is not an ``async def`` function.
        ValueError: if a different function is already registered under
            ``fn.__name__`` (registering the same object twice is a no-op).
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"register_tool expected an async function, got {type(fn).__name__} "
            f"for {getattr(fn, '__name__', fn)!r}. Tool functions must be "
            f"'async def' and return a ToolResult."
        )
    name = fn.__name__
    existing = _extra_tools.get(name)
    if existing is not None and existing is not fn:
        raise ValueError(
            f"tool name {name!r} is already registered to a different function"
        )
    _extra_tools[name] = fn
    return fn


def get_extra_tools() -> List[ToolFn]:
    """Return a list of currently registered extra tools."""
    return list(_extra_tools.values())


def clear_extra_tools() -> None:
    """Reset the registry. Intended for tests."""
    _extra_tools.clear()
