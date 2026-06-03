from pathlib import Path

from cli_textual.tools._editblock import replace_most_similar_chunk
from cli_textual.tools.base import ToolResult
from cli_textual.tools.write_file import _resolve_in_workspace


async def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    workspace_root: Path | None = None,
) -> ToolResult:
    """Replace ``old_string`` with ``new_string`` in a file.

    Interface mirrors opencode's ``edit`` tool; matching is forgiving (ported
    from Aider) so edits survive whitespace drift and ``...`` elisions instead
    of failing on a byte-for-byte mismatch.

    - Errors if ``old_string`` is not found.
    - Errors if ``old_string`` matches multiple times, unless ``replace_all``.
    - Pass ``new_string=""`` to delete the matched text.
    - Path is jailed to the workspace directory.

    Args:
        path: File path (relative to the workspace or absolute).
        old_string: Exact text to find (include enough context to be unique).
        new_string: Replacement text.
        replace_all: Replace every occurrence instead of requiring a unique match.
    """
    try:
        _, file_path = _resolve_in_workspace(path, workspace_root)
    except PermissionError as exc:
        return ToolResult(output=f"Error: {exc}", is_error=True)

    if old_string == "":
        return ToolResult(
            output="Error: old_string must not be empty (use write_file to create/replace a file)",
            is_error=True,
        )

    if not file_path.exists():
        return ToolResult(output=f"Error: file not found: {path}", is_error=True)

    try:
        # Strict decode: silently round-tripping a non-UTF-8 file with
        # errors="replace" would corrupt its bytes on write.
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolResult(output=f"Error: {path} is not valid UTF-8 text", is_error=True)
    except Exception as exc:
        return ToolResult(output=f"Error reading file: {exc}", is_error=True)

    if old_string == new_string:
        return ToolResult(output="Error: old_string and new_string are identical", is_error=True)

    count = content.count(old_string)

    if replace_all:
        if count == 0:
            return ToolResult(output="Error: old_string not found", is_error=True)
        new_content = content.replace(old_string, new_string)
        replaced = count
    elif count == 1:
        new_content = content.replace(old_string, new_string, 1)
        replaced = 1
    elif count > 1:
        return ToolResult(
            output=(
                f"Error: found {count} matches for old_string. Provide more "
                "surrounding context to identify a unique match, or set replace_all=True."
            ),
            is_error=True,
        )
    else:
        # No exact match — fall back to Aider's forgiving matcher (whitespace
        # drift, dropped blank line, ... elision). Replaces a single chunk.
        new_content = replace_most_similar_chunk(content, old_string, new_string)
        if new_content is None:
            return ToolResult(output="Error: old_string not found", is_error=True)
        replaced = 1

    try:
        file_path.write_text(new_content, encoding="utf-8")
    except Exception as exc:
        return ToolResult(output=f"Error writing file: {exc}", is_error=True)

    suffix = " (all occurrences)" if replace_all and replaced > 1 else ""
    return ToolResult(output=f"Edited {path}: {replaced} replacement(s){suffix}")
