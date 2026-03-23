from pathlib import Path
from cli_textual.tools.base import ToolResult

MAX_CHARS = 8192
MAX_LINES = 200


async def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> ToolResult:
    """Read the contents of a local file, optionally restricted to a line range.

    Capped at 200 lines / 8 KB.
    """
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line if end_line is not None else len(lines))
        end = min(end, start + MAX_LINES)
        selected = lines[start:end]
        content = "\n".join(selected)
        truncated = ""
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
            truncated = "\n[truncated]"
        return ToolResult(output=content + truncated)
    except Exception as exc:
        return ToolResult(output=f"Error reading file: {exc}", is_error=True)
