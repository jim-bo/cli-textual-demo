"""File-finding tool — structured glob, a clean alternative to `find` via bash.

Read-only and workspace-jailed. Results sorted by modification time (most
recent first), matching how coding agents typically surface "relevant" files.
"""
from pathlib import Path

from cli_textual.tools.base import ToolResult
from cli_textual.tools.write_file import _resolve_in_workspace

MAX_CHARS = 8192
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}


async def glob(
    pattern: str,
    path: str = ".",
    max_results: int = 100,
    workspace_root: Path | None = None,
) -> ToolResult:
    """Find files matching a glob pattern (supports ``**`` for recursion).

    Returns workspace-relative paths, newest first. Path is jailed to the
    workspace.

    Args:
        pattern: Glob pattern, e.g. ``**/*.py`` or ``src/**/test_*.py``.
        path: Directory to search under (relative to workspace or absolute).
        max_results: Cap on number of paths returned (default 100).
    """
    try:
        workspace, base = _resolve_in_workspace(path, workspace_root)
    except PermissionError as exc:
        return ToolResult(output=f"Error: {exc}", is_error=True)
    if not base.exists():
        return ToolResult(output=f"Error: path not found: {path}", is_error=True)

    hits = [
        p for p in base.glob(pattern)
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.relative_to(base).parts)
    ]
    try:
        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        hits.sort()

    if not hits:
        return ToolResult(output=f"No files matching {pattern!r}")
    rels = [str(p.relative_to(workspace)) for p in hits[:max_results]]
    out = "\n".join(rels)
    truncated = ""
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS]
        truncated = "\n[truncated]"
    note = f"\n[showing {max_results} of {len(hits)}]" if len(hits) > max_results else ""
    return ToolResult(output=out + truncated + note)
