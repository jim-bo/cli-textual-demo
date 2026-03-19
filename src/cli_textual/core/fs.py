import os
import json
from pathlib import Path

class FSManager:
    """Handles file system validation and jailing."""
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def validate_path(self, path_str: str) -> Path | None:
        """Ensures the path is within the workspace root."""
        try:
            target = (self.workspace_root / path_str).resolve()
            if self.workspace_root in target.parents or target == self.workspace_root:
                return target
        except:
            pass
        return None
