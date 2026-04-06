# NOTE: we intentionally do NOT re-export ``manager_agent`` here. Doing so
# would resolve the PEP 562 ``__getattr__`` shim in ``manager.py`` at package
# import time and build the agent before user code has a chance to call
# ``register_tool()`` or ``set_model()``. Consumers that still want the legacy
# name should import it directly: ``from cli_textual.agents.manager import
# manager_agent`` (which defers the build until that statement runs).
from cli_textual.agents.manager import get_agent, run_manager_pipeline
from cli_textual.agents.model import get_model, set_model

__all__ = [
    "get_agent",
    "run_manager_pipeline",
    "get_model",
    "set_model",
]
