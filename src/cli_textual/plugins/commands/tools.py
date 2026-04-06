from typing import List
from textual import on
from textual.app import ComposeResult
from textual.widgets import Label, OptionList, Static
from textual.widget import Widget
from cli_textual.core.command import SlashCommand
from cli_textual.agents.manager import get_agent


def _first_line(text: str) -> str:
    """Return the first non-empty line of a docstring."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


class ToolsWidget(Widget):
    """Self-contained widget: shows tool list, then full description on selection."""

    DEFAULT_CSS = """
    ToolsWidget {
        height: auto;
        padding: 0 1;
    }
    ToolsWidget .tool-detail {
        padding: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Agent tools  (Enter to inspect, Esc to close)")
        tools = get_agent()._function_toolset.tools
        items = [
            f"{name:<22} {_first_line(tool.description)}"
            for name, tool in tools.items()
        ]
        yield OptionList(*items, id="tools-option-list")

    @on(OptionList.OptionSelected, "#tools-option-list")
    def show_detail(self, event: OptionList.OptionSelected) -> None:
        tool_name = str(event.option.prompt).split()[0]
        tools = get_agent()._function_toolset.tools
        tool = tools.get(tool_name)
        description = tool.description if tool else "(no description)"

        self.query("*").remove()
        self.mount(Label(f"[bold]{tool_name}[/bold]  (Esc to close)"))
        self.mount(Static(description, classes="tool-detail"))


class ToolsCommand(SlashCommand):
    name = "/tools"
    description = "List available agent tools"

    async def execute(self, app, args: List[str]):
        container = app.query_one("#interaction-container")
        container.add_class("visible")
        container.query("*").remove()
        widget = ToolsWidget()
        container.mount(widget)
        app.call_after_refresh(
            lambda: widget.query_one("#tools-option-list").focus()
        )
