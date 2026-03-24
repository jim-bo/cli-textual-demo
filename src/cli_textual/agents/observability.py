"""Optional Langfuse observability — activates only when credentials are set."""

import os
import logging
from contextlib import nullcontext

from pydantic_ai import Agent

logger = logging.getLogger(__name__)

_initialized = False
_tracing_enabled = False


def init_observability():
    """Initialize Langfuse tracing if credentials are configured.

    Requires LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY env vars.
    LANGFUSE_BASE_URL defaults to https://cloud.langfuse.com.
    Safe to call multiple times — only initializes once.
    """
    global _initialized, _tracing_enabled
    if _initialized:
        return
    _initialized = True

    secret = os.getenv("LANGFUSE_SECRET_KEY")
    public = os.getenv("LANGFUSE_PUBLIC_KEY")
    if not secret or not public:
        logger.debug("Langfuse credentials not set — tracing disabled")
        return

    try:
        from langfuse import get_client

        client = get_client()
        if client.auth_check():
            Agent.instrument_all()
            _tracing_enabled = True
            logger.info("Langfuse tracing enabled")
        else:
            logger.warning("Langfuse auth check failed — tracing disabled")
    except Exception as e:
        logger.warning("Langfuse init failed: %s — tracing disabled", e)


def trace_context(prompt: str, session_id: str | None = None):
    """Return a Langfuse observation context if tracing is active, else a no-op."""
    if not _tracing_enabled:
        return nullcontext()
    try:
        from langfuse import get_client

        client = get_client()
        return client.start_as_current_observation(
            as_type="trace",
            name="manager-pipeline",
            session_id=session_id,
            input=prompt,
        )
    except Exception:
        return nullcontext()
