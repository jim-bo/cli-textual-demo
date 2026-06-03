"""Todo-list scratchpad — lets the agent plan and track multi-step work.

Stateless by design: the model passes the FULL current list on every call (the
list lives in the conversation, same convention as opencode/Claude Code's
todowrite). The tool validates and renders it; the rendered checklist is what
keeps a long, multi-step run organized instead of thrashing.
"""
from cli_textual.tools.base import ToolResult

_STATUSES = {"pending", "in_progress", "completed"}
_MARKER = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


async def todo_write(todos: list[dict[str, str]]) -> ToolResult:
    """Record/replace the current todo list and render it as a checklist.

    Pass the entire list each call (it replaces the previous one). Use this to
    plan a multi-step task up front and to mark progress as you go.

    Args:
        todos: A list of items, each ``{"content": <str>, "status": <str>}``
            where status is one of: pending, in_progress, completed.
    """
    if not isinstance(todos, list) or not todos:
        return ToolResult(output="Error: todos must be a non-empty list", is_error=True)

    lines = []
    for i, item in enumerate(todos, 1):
        if not isinstance(item, dict) or "content" not in item:
            return ToolResult(output=f"Error: todo #{i} must have a 'content' field", is_error=True)
        status = item.get("status", "pending")
        if status not in _STATUSES:
            return ToolResult(
                output=f"Error: todo #{i} status {status!r} invalid (use {sorted(_STATUSES)})",
                is_error=True,
            )
        lines.append(f"{_MARKER[status]} {item['content']}")

    done = sum(1 for t in todos if t.get("status") == "completed")
    return ToolResult(output="\n".join(lines) + f"\n({done}/{len(todos)} complete)")
