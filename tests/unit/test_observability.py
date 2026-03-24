"""Tests for optional Langfuse observability integration.

These tests avoid importing the real langfuse module (which registers global
OTel tracer providers that contaminate pydantic-ai FunctionModel in other tests).
Instead, we inject a fake langfuse module via sys.modules.
"""

import sys
import types
import pytest
from contextlib import nullcontext
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _reset_init_flag():
    """Reset the module-level flags between tests."""
    import cli_textual.agents.observability as obs
    obs._initialized = False
    obs._tracing_enabled = False
    yield
    obs._initialized = False
    obs._tracing_enabled = False


def _make_fake_langfuse(mock_client):
    """Create a fake langfuse module that returns mock_client from get_client()."""
    fake = types.ModuleType("langfuse")
    fake.get_client = lambda: mock_client
    return fake


def test_init_noop_without_keys(monkeypatch):
    """No Langfuse env vars → no error, instrument_all not called."""
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    with patch("pydantic_ai.Agent.instrument_all") as mock_instrument:
        from cli_textual.agents.observability import init_observability
        init_observability()
        mock_instrument.assert_not_called()


def test_init_calls_instrument_all(monkeypatch):
    """Both keys set + auth passes → Agent.instrument_all() called."""
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")

    mock_client = MagicMock()
    mock_client.auth_check.return_value = True
    fake = _make_fake_langfuse(mock_client)

    with patch("pydantic_ai.Agent.instrument_all") as mock_instrument, \
         patch.dict(sys.modules, {"langfuse": fake}):
        from cli_textual.agents.observability import init_observability
        init_observability()
        mock_instrument.assert_called_once()


def test_init_idempotent(monkeypatch):
    """Calling init_observability() twice only initializes once."""
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")

    mock_client = MagicMock()
    mock_client.auth_check.return_value = True
    fake = _make_fake_langfuse(mock_client)

    with patch("pydantic_ai.Agent.instrument_all") as mock_instrument, \
         patch.dict(sys.modules, {"langfuse": fake}):
        from cli_textual.agents.observability import init_observability
        init_observability()
        init_observability()
        mock_instrument.assert_called_once()


def test_init_handles_auth_failure(monkeypatch):
    """Auth check returns False → logs warning, no crash."""
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")

    mock_client = MagicMock()
    mock_client.auth_check.return_value = False
    fake = _make_fake_langfuse(mock_client)

    with patch("pydantic_ai.Agent.instrument_all") as mock_instrument, \
         patch.dict(sys.modules, {"langfuse": fake}):
        from cli_textual.agents.observability import init_observability
        init_observability()
        mock_instrument.assert_not_called()


def test_trace_context_noop_when_tracing_disabled():
    """trace_context() returns nullcontext when tracing is not enabled."""
    from cli_textual.agents.observability import trace_context
    ctx = trace_context("test prompt")
    assert isinstance(ctx, nullcontext)


def test_trace_context_returns_observation_when_enabled():
    """trace_context() returns a Langfuse observation when tracing is enabled."""
    import cli_textual.agents.observability as obs
    obs._tracing_enabled = True

    mock_observation = MagicMock()
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value = mock_observation
    fake = _make_fake_langfuse(mock_client)

    with patch.dict(sys.modules, {"langfuse": fake}):
        from cli_textual.agents.observability import trace_context
        ctx = trace_context("test prompt", session_id="sess-123")
        assert ctx is mock_observation
        mock_client.start_as_current_observation.assert_called_once_with(
            as_type="trace",
            name="manager-pipeline",
            session_id="sess-123",
            input="test prompt",
        )


def test_trace_context_returns_nullcontext_on_exception():
    """trace_context() returns nullcontext when client raises an exception."""
    import cli_textual.agents.observability as obs
    obs._tracing_enabled = True

    mock_client = MagicMock()
    mock_client.start_as_current_observation.side_effect = RuntimeError("connection failed")
    fake = _make_fake_langfuse(mock_client)

    with patch.dict(sys.modules, {"langfuse": fake}):
        from cli_textual.agents.observability import trace_context
        ctx = trace_context("test prompt")
        assert isinstance(ctx, nullcontext)
