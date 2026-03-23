from dataclasses import dataclass


@dataclass
class ToolResult:
    """Return type for all pure tool functions."""
    output: str
    is_error: bool = False
    exit_code: int | None = None
