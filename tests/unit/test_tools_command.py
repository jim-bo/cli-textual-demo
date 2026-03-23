import pytest
from unittest.mock import patch, MagicMock
from pydantic_ai.models.test import TestModel
from textual.widgets import Label, OptionList, Static
from cli_textual.app import ChatApp
from cli_textual.plugins.commands.tools import ToolsWidget, ToolsCommand, _first_line
from cli_textual.agents.orchestrators import manager_agent


# ---------------------------------------------------------------------------
# _first_line helper
# ---------------------------------------------------------------------------

def test_first_line_returns_first_non_empty():
    assert _first_line("\n\n  Hello world\n  more text") == "Hello world"

def test_first_line_empty_string():
    assert _first_line("") == ""

def test_first_line_only_whitespace():
    assert _first_line("   \n  \n") == ""


# ---------------------------------------------------------------------------
# ToolsWidget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_widget_composes_option_list():
    """ToolsWidget should render an OptionList with one item per tool."""
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        widget = ToolsWidget()
        history = app.query_one("#history-container")
        await history.mount(widget)
        await pilot.pause(0.1)

        option_list = widget.query_one("#tools-option-list", OptionList)
        assert option_list is not None

        tool_count = len(manager_agent._function_toolset.tools)
        assert option_list.option_count == tool_count


@pytest.mark.asyncio
async def test_tools_widget_shows_detail_on_selection():
    """Selecting a tool in the OptionList should swap to the detail view."""
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        widget = ToolsWidget()
        history = app.query_one("#history-container")
        await history.mount(widget)
        await pilot.pause(0.1)

        option_list = widget.query_one("#tools-option-list", OptionList)
        option_list.focus()
        await pilot.pause(0.05)

        # Select the first item
        await pilot.press("enter")
        await pilot.pause(0.2)

        # OptionList should be gone, Static detail should be present
        assert not widget.query("#tools-option-list")
        assert widget.query(".tool-detail")


@pytest.mark.asyncio
async def test_tools_widget_detail_contains_tool_name():
    """Detail view Label should contain the selected tool's name."""
    first_tool_name = next(iter(manager_agent._function_toolset.tools))

    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        widget = ToolsWidget()
        history = app.query_one("#history-container")
        await history.mount(widget)
        await pilot.pause(0.1)

        option_list = widget.query_one("#tools-option-list", OptionList)
        option_list.focus()
        await pilot.pause(0.05)
        await pilot.press("enter")
        await pilot.pause(0.2)

        labels = list(widget.query(Label))
        assert any(first_tool_name in str(lbl.render()) for lbl in labels)


# ---------------------------------------------------------------------------
# ToolsCommand integration with ChatApp
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_command_mounts_widget():
    """/tools command should mount ToolsWidget into #interaction-container."""
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press(*"/tools", "enter")
        await pilot.pause(0.3)

        container = app.query_one("#interaction-container")
        assert "visible" in container.classes
        assert container.query(ToolsWidget)
