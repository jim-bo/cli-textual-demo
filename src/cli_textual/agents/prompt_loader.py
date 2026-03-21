import yaml
from pathlib import Path

def load_prompts():
    """Load agent prompts from the configuration YAML."""
    prompt_path = Path(__file__).parent / "prompts.yaml"
    if not prompt_path.exists():
        return {}
    
    with open(prompt_path, "r") as f:
        return yaml.safe_load(f)

# Global prompts registry
PROMPTS = load_prompts()
