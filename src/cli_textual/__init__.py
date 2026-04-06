"""cli_textual — reusable framework for building AI agent TUIs."""
from cli_textual.app import ChatApp
from cli_textual.core.chat_events import ChatDeps
from cli_textual.core.command import CommandManager, SlashCommand
from cli_textual.tools.base import ToolResult
from cli_textual.tools.registry import register_tool

__all__ = [
    "ChatApp",
    "ToolResult",
    "register_tool",
    "SlashCommand",
    "CommandManager",
    "ChatDeps",
]
