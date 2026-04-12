"""Tests for ChatApp customization hooks.

Covers three subclass-friendly hooks added so third-party apps can rebrand
the TUI without monkey-patching the cli_textual package:

1. ``CSS_PATH`` — absolute path so subclasses inherit it correctly
2. ``LANDING_WIDGET_CLS`` — class attr to swap the landing-page widget
3. ``command_filter`` — constructor arg to restrict the active command set
"""
import os
from pathlib import Path

import pytest
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label, Static

from cli_textual.app import ChatApp
from cli_textual.ui.widgets.landing_page import LandingPage

pytestmark = pytest.mark.timeout(5)


# ---------------------------------------------------------------------------
# CSS_PATH absolute
# ---------------------------------------------------------------------------


def test_css_path_is_absolute():
    """CSS_PATH must be absolute so subclasses inherit it correctly.

    Textual resolves relative ``CSS_PATH`` strings against the module file
    where the class is defined. If ``ChatApp.CSS_PATH`` were the literal
    ``"app.tcss"``, a subclass in a different package would look for
    ``<their_package>/app.tcss`` and crash at startup.
    """
    assert os.path.isabs(ChatApp.CSS_PATH), (
        f"CSS_PATH must be absolute, got {ChatApp.CSS_PATH!r}"
    )
    assert Path(ChatApp.CSS_PATH).exists(), (
        f"CSS_PATH points at a non-existent file: {ChatApp.CSS_PATH}"
    )
    assert Path(ChatApp.CSS_PATH).name == "app.tcss"


def test_css_path_inherited_by_subclass():
    """A subclass defined in another module inherits the absolute path."""

    class MyApp(ChatApp):
        pass

    assert MyApp.CSS_PATH == ChatApp.CSS_PATH
    assert Path(MyApp.CSS_PATH).exists()


# ---------------------------------------------------------------------------
# LANDING_WIDGET_CLS
# ---------------------------------------------------------------------------


class _CustomLanding(Static):
    """Marker widget used to verify the subclass override took effect."""

    def compose(self) -> ComposeResult:
        with Container(id="landing-container"):
            yield Label("custom landing page", id="custom-landing-marker")


@pytest.mark.asyncio
async def test_landing_widget_cls_default_is_landing_page(monkeypatch):
    """Without an override, the default ``LandingPage`` is mounted."""
    # The agent model is constructed lazily on app start; give it a
    # placeholder key so OpenAI client construction doesn't explode in CI.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert ChatApp.LANDING_WIDGET_CLS is LandingPage

    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        history = app.query_one("#history-container")
        assert list(history.query(LandingPage)), (
            "default LandingPage should be mounted"
        )


@pytest.mark.asyncio
async def test_landing_widget_cls_subclass_override(monkeypatch):
    """A subclass setting ``LANDING_WIDGET_CLS`` mounts its own widget and
    the default ``LandingPage`` is *not* mounted alongside it."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class MyApp(ChatApp):
        LANDING_WIDGET_CLS = _CustomLanding

    app = MyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        history = app.query_one("#history-container")

        assert list(history.query(_CustomLanding)), (
            "custom landing widget should be mounted"
        )
        assert not list(history.query(LandingPage)), (
            "default LandingPage must not be mounted when the subclass "
            "overrides LANDING_WIDGET_CLS"
        )


# ---------------------------------------------------------------------------
# command_filter
# ---------------------------------------------------------------------------


def test_command_filter_none_keeps_all_commands():
    """With no filter, every auto-discovered built-in is registered."""
    app = ChatApp()
    cmds = set(app.command_manager.commands.keys())
    # The built-ins shipped in cli_textual.plugins.commands should all be here.
    assert "/help" in cmds
    assert "/clear" in cmds
    assert "/mode" in cmds


def test_command_filter_restricts_commands():
    """A ``command_filter`` predicate drops commands that return False."""
    allowed = {"/help", "/clear"}

    app = ChatApp(command_filter=lambda name: name in allowed)
    registered = set(app.command_manager.commands.keys())

    assert registered == allowed, (
        f"expected exactly {allowed}, got {registered}"
    )


def test_command_filter_applies_after_custom_packages():
    """The filter applies uniformly across built-ins *and* user packages."""
    # A filter that only keeps "/help" must drop every other built-in.
    app = ChatApp(
        command_filter=lambda name: name == "/help",
    )
    assert set(app.command_manager.commands.keys()) == {"/help"}


def test_command_filter_receives_lowercased_name():
    """Confirm the filter callable receives the same key the manager uses
    for dispatch — this pins the API contract."""
    seen = []

    def _filter(name: str) -> bool:
        seen.append(name)
        return True

    ChatApp(command_filter=_filter)

    assert seen, "filter was never called"
    # CommandManager stores names lowercased; the filter must see the same.
    for name in seen:
        assert name == name.lower(), (
            f"filter received non-lowercased name: {name!r}"
        )
