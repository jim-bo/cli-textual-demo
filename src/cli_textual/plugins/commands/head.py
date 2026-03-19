from pathlib import Path
from typing import List
from textual.widgets import Static, Label
from rich.syntax import Syntax
from cli_textual.core.command import SlashCommand

class HeadCommand(SlashCommand):
    name = "/head"
    description = "Secure file viewer"
    requires_permission = True

    async def execute(self, app, args: List[str]):
        if not args:
            app.add_to_history("**Error**: /head <file>")
            return
        
        target = app.fs_manager.validate_path(args[0])
        if not target:
            app.add_to_history("**Access denied**.")
            return
        
        if not target.is_file():
            app.add_to_history(f"**Error**: {target} is not a file.")
            return

        lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        
        container = app.query_one("#interaction-container")
        container.add_class("visible")
        container.query("*").remove()
        
        try:
            content = ""
            with open(target, "r") as f:
                for _ in range(lines):
                    l = f.readline()
                    if not l: break
                    content += l
            
            container.mount(Label(f"Head of {target.name}: (Esc to close)"))
            container.mount(Static(Syntax(content, target.suffix.strip("."), theme="monokai", line_numbers=True), classes="file-viewer"))
        except Exception as e:
            app.add_to_history(f"**Error**: {e}")
