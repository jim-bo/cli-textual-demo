from pathlib import Path

from cli_textual.tools.base import ToolResult


def _resolve_in_workspace(path: str, workspace_root: Path | None) -> tuple[Path, Path]:
    """Resolve ``path`` against the workspace and enforce jailing.

    Returns ``(workspace, file_path)``. Raises ``PermissionError`` if the
    resolved path escapes the workspace directory.
    """
    workspace = (workspace_root or Path.cwd()).resolve()
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = workspace / file_path
    file_path = file_path.resolve()
    if workspace not in file_path.parents and file_path != workspace:
        raise PermissionError("access denied — path outside workspace")
    return workspace, file_path


async def write_file(path: str, content: str, workspace_root: Path | None = None) -> ToolResult:
    """Create or overwrite a file with ``content``.

    Parent directories are created as needed. Path is jailed to the workspace
    directory.

    Args:
        path: File path (relative to the workspace or absolute).
        content: Full file contents to write.
    """
    try:
        _, file_path = _resolve_in_workspace(path, workspace_root)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        existed = file_path.exists()
        file_path.write_text(content, encoding="utf-8")
        verb = "Updated" if existed else "Created"
        nbytes = len(content.encode("utf-8"))
        return ToolResult(output=f"{verb} {path} ({nbytes} bytes)")
    except PermissionError as exc:
        return ToolResult(output=f"Error: {exc}", is_error=True)
    except Exception as exc:
        return ToolResult(output=f"Error writing file: {exc}", is_error=True)
