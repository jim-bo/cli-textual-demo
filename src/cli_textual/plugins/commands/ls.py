import os
import datetime
from pathlib import Path
from typing import List
from textual.widgets import DataTable, Label
from cli_textual.core.command import SlashCommand

class ListDirectoryCommand(SlashCommand):
    name = "/ls"
    description = "Secure directory listing"
    requires_permission = True

    async def execute(self, app, args: List[str]):
        path_str = args[0] if args else "."
        target = app.fs_manager.validate_path(path_str)
        
        if not target:
            app.add_to_history("**Access denied**: Path outside workspace.")
            return

        container = app.query_one("#interaction-container")
        container.add_class("visible")
        container.query("*").remove()
        container.mount(Label(f"Listing {target}: (Esc to close)"))
        
        table = DataTable(id="ls-table")
        table.cursor_type = "row"
        table.add_columns("Name", "Size", "Modified")
        
        try:
            # Sort: Directories first, then alphabetically
            items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for item in items:
                stats = item.stat()
                size = f"{stats.st_size / 1024:.1f} KB" if item.is_file() else "(dir)"
                mtime = datetime.datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                icon = "📁" if item.is_dir() else "📄"
                table.add_row(f"{icon} {item.name}", size, mtime, key=str(item))
            
            container.mount(table)
            app.call_after_refresh(table.focus)
        except Exception as e:
            app.add_to_history(f"**Error**: {e}")
