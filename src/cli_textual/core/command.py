import importlib
import pkgutil
import inspect
from abc import ABC, abstractmethod
from typing import List, Dict, Type

class SlashCommand(ABC):
    """Base class for all slash commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The command string, e.g., '/help'."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief summary of what the command does."""
        pass

    @property
    def requires_permission(self) -> bool:
        """True if this command needs explicit user approval before running."""
        return False

    @abstractmethod
    async def execute(self, app, args: List[str]):
        """The logic to run when the command is invoked."""
        pass

class CommandManager:
    """Registry and executor for slash commands."""

    def __init__(self):
        self.commands: Dict[str, SlashCommand] = {}

    def register_command(self, cmd: SlashCommand):
        """Manually register a command instance."""
        self.commands[cmd.name.lower()] = cmd

    def auto_discover(self, package_path: str):
        """
        Dynamically discover and register SlashCommand classes in a package.
        e.g., auto_discover('cli_textual.plugins.commands')
        """
        try:
            package = importlib.import_module(package_path)
            for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
                full_module_name = f"{package_path}.{name}"
                module = importlib.import_module(full_module_name)

                for _, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, SlashCommand) and 
                        obj is not SlashCommand):
                        # Instantiate and register
                        instance = obj()
                        self.register_command(instance)
        except Exception as e:
            print(f"Error during command discovery: {e}")

    def get_command(self, name: str) -> SlashCommand:
        return self.commands.get(name.lower())

    def get_all_help(self) -> str:
        help_text = "### Commands\n"
        for name in sorted(self.commands.keys()):
            cmd = self.commands[name]
            help_text += f"- {name.ljust(15)} {cmd.description}\n"
        return help_text

