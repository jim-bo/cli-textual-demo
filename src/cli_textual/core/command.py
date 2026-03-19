from abc import ABC, abstractmethod
from typing import List

class SlashCommand(ABC):
    """Base class for all slash commands."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The command string (e.g., /ls)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Help text for the command."""
        pass

    @property
    def requires_permission(self) -> bool:
        """Whether this command needs explicit user authorization."""
        return False

    @abstractmethod
    async def execute(self, app, args: List[str]):
        """The implementation of the command."""
        pass

class CommandManager:
    """Registry and orchestrator for slash commands."""
    
    def __init__(self):
        self.commands = {}

    def register_command(self, cmd: SlashCommand):
        self.commands[cmd.name] = cmd

    def get_command(self, name: str) -> SlashCommand | None:
        return self.commands.get(name)

    def get_all_help(self) -> str:
        help_text = "### Commands\n"
        for name in sorted(self.commands.keys()):
            cmd = self.commands[name]
            help_text += f"- {name.ljust(15)} {cmd.description}\n"
        return help_text
