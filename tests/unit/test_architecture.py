"""Architecture boundary tests: prove tools/ has no TUI dependencies."""
import ast
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "src" / "cli_textual" / "tools"


def _all_imports(directory: Path) -> list[str]:
    """Extract all import strings from .py files in a directory."""
    imports = []
    for py_file in directory.glob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
    return imports


def test_tools_module_has_no_event_imports():
    """tools/ must not import from chat_events (TUI contract)."""
    imports = _all_imports(TOOLS_DIR)
    violations = [i for i in imports if "chat_events" in i]
    assert not violations, f"tools/ imports chat_events: {violations}"


def test_tools_module_has_no_queue_imports():
    """tools/ must not use asyncio.Queue (TUI plumbing)."""
    for py_file in TOOLS_DIR.glob("*.py"):
        source = py_file.read_text()
        assert "asyncio.Queue" not in source, f"{py_file.name} references asyncio.Queue"
