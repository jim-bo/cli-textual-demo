import os
import json
from pathlib import Path

class PermissionManager:
    """Handles persistent tool execution approvals."""
    def __init__(self, settings_path: Path):
        self.settings_path = settings_path

    def is_tool_approved(self, tool: str) -> bool:
        if not self.settings_path.exists():
            return False
        try:
            with open(self.settings_path, "r") as f:
                data = json.load(f)
                return tool in data.get("approved_tools", [])
        except:
            return False

    def approve_tool(self, tool: str):
        os.makedirs(self.settings_path.parent, exist_ok=True)
        data = {"approved_tools": []}
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r") as f:
                    data = json.load(f)
            except:
                pass
        if tool not in data["approved_tools"]:
            data["approved_tools"].append(tool)
        with open(self.settings_path, "w") as f:
            json.dump(data, f)
