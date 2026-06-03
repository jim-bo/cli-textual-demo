"""Content search tool — a structured, token-cheap alternative to `grep` via bash.

Pure stdlib (no ripgrep dependency); early-exits once `max_results` matches are
found so it stays fast even on large trees. Read-only and workspace-jailed.
"""
import re
from pathlib import Path

from cli_textual.tools.base import ToolResult
from cli_textual.tools.write_file import _resolve_in_workspace

MAX_CHARS = 8192
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache", "target", "dist", "build"}


async def grep(
    pattern: str,
    path: str = ".",
    ignore_case: bool = False,
    max_results: int = 100,
    workspace_root: Path | None = None,
) -> ToolResult:
    """Search file contents for a regular expression, returning ``file:line: text``.

    Recursively searches under ``path``. Skips VCS/build dirs and binary files.
    Capped at ``max_results`` matches. Path is jailed to the workspace.

    Args:
        pattern: Regular expression to search for.
        path: File or directory to search under (relative to workspace or absolute).
        ignore_case: Case-insensitive match when True.
        max_results: Stop after this many matching lines (default 100).
    """
    try:
        regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        return ToolResult(output=f"Error: invalid regex: {exc}", is_error=True)

    try:
        workspace, base = _resolve_in_workspace(path, workspace_root)
    except PermissionError as exc:
        return ToolResult(output=f"Error: {exc}", is_error=True)
    if not base.exists():
        return ToolResult(output=f"Error: path not found: {path}", is_error=True)

    files = [base] if base.is_file() else sorted(
        p for p in base.rglob("*")
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.relative_to(base).parts)
    )

    matches: list[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # skip binary / unreadable
        rel = f.relative_to(workspace)
        for n, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{rel}:{n}: {line.strip()[:200]}")
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(output=f"No matches for {pattern!r}")
    out = "\n".join(matches)
    truncated = ""
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS]
        truncated = "\n[truncated]"
    note = f"\n[stopped at {max_results} matches]" if len(matches) >= max_results else ""
    return ToolResult(output=out + truncated + note)
