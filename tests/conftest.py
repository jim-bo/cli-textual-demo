import os
import json
import pytest
from pathlib import Path

# Ensure we can import from the root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(autouse=True)
def setup_permissions():
    """Automatically approve all tools before every test."""
    workspace_root = Path.cwd().resolve()
    settings_dir = workspace_root / ".cbio"
    settings_path = settings_dir / "settings.json"
    
    os.makedirs(settings_dir, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump({
            "approved_tools": ["/ls", "/head", "/select", "/load", "/survey", "/clear"]
        }, f)
    yield
    # Cleanup if needed
