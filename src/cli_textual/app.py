import asyncio
import time
from pathlib import Path

from textual import on, events
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import (
    Header, Footer, Static, Markdown, Label, OptionList, 
    TabbedContent, DirectoryTree, DataTable
)
from textual.widgets.option_list import Option
from textual.binding import Binding

# Core Framework Imports
from cli_textual.core.fs import FSManager
from cli_textual.core.permissions import PermissionManager
from cli_textual.core.command import CommandManager
from cli_textual.core.dummy_agent import DummyAgent
from cli_textual.core.chat_events import (
    AgentThinking, AgentToolStart, AgentToolEnd, AgentStreamChunk, AgentComplete
)

# UI Component Imports
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from cli_textual.ui.widgets.dna_spinner import DNASpinner
from cli_textual.ui.screens.permission_screen import PermissionScreen

# Plugin Imports (Simulated auto-discovery for now)
from cli_textual.plugins.commands.ls import ListDirectoryCommand
from cli_textual.plugins.commands.head import HeadCommand
from cli_textual.plugins.commands.clear import ClearCommand
from cli_textual.plugins.commands.load import LoadCommand
from cli_textual.plugins.commands.select import SelectCommand
from cli_textual.plugins.commands.survey import SurveyCommand

class ChatApp(App):
    """Refactored ChatApp using modular architecture."""

    CSS = """
    Screen { background: #121212; padding-bottom: 1; }
    #history-container { height: 1fr; padding: 1; overflow-y: scroll; }
    .user-msg { color: #00FF00; margin-top: 1; text-style: bold; }
    .ai-msg { color: #CCCCCC; margin-bottom: 1; border-left: solid #333333; padding-left: 1; }
    #interaction-container { display: none; border-top: tall #333333; background: #1A1A1A; }
    #interaction-container.visible { display: block; padding: 1; min-height: 10; }
    #task-area { height: 3; align: left middle; }
    DNASpinner { width: 5; height: 1; color: #00AAFF; text-style: bold; }
    #task-label { margin-left: 2; }
    #bottom-dock { dock: bottom; height: auto; background: #121212; }
    #input-container { height: auto; min-height: 3; background: #2A2A2A; margin: 0 1; align: left top; }
    #prompt { color: #D4AF37; margin-left: 1; margin-top: 1; text-style: bold; }
    GrowingTextArea { border: none; background: #2A2A2A; width: 1fr; height: 1; margin-top: 1; }
    GrowingTextArea:focus { border: none; }
    .status-info { color: #888888; margin-left: 1; margin-top: 1; }
    .path-info { color: #FFFFFF; margin-left: 1; }
    #autocomplete-list { background: #1E1E1E; color: #CCCCCC; border: none; height: auto; max-height: 8; display: none; margin: 0 1; }
    #autocomplete-list.visible { display: block; }
    OptionList { height: 8; border: round #00AAFF; }
    Footer { background: transparent; color: #666666; }
    .cancel-note { color: #666666; text-style: italic; margin-left: 1; }
    TabbedContent { height: 12; margin: 1; }
    DirectoryTree { height: 20; background: #1A1A1A; border: round #333333; overflow-y: auto; }
    .file-viewer { height: 20; background: #000000; padding: 1; overflow-y: scroll; border: solid #333333; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+d", "double_ctrl_d", "Exit", show=True, priority=True),
        Binding("escape", "cancel_interaction", "Cancel", show=False),
        Binding("ctrl+n", "next_tab", "Next Tab", show=False, priority=True),
        Binding("ctrl+p", "prev_tab", "Prev Tab", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.last_ctrl_d_time = 0
        self.survey_answers = {}
        
        # Initialize Core Managers
        self.workspace_root = Path.cwd().resolve()
        self.fs_manager = FSManager(self.workspace_root)
        self.permission_manager = PermissionManager(self.workspace_root / ".cbio" / "settings.json")
        self.command_manager = CommandManager()
        self.agent = DummyAgent()
        
        # Register Commands
        self._init_commands()

    def _init_commands(self):
        self.command_manager.register_command(ListDirectoryCommand())
        self.command_manager.register_command(HeadCommand())
        self.command_manager.register_command(ClearCommand())
        self.command_manager.register_command(LoadCommand())
        self.command_manager.register_command(SelectCommand())
        self.command_manager.register_command(SurveyCommand())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="history-container"):
            yield Static("Welcome to the Modular TUI Framework.", classes="ai-msg")
        with Container(id="interaction-container"): pass
        with Container(id="bottom-dock"):
            with Horizontal(id="input-container"):
                yield Label("> ", id="prompt"); yield GrowingTextArea(id="main-input")
            yield OptionList(id="autocomplete-list")
            yield Label("workspace (/directory)", classes="status-info")
            yield Label(str(self.workspace_root), classes="path-info")
            yield Footer()

    def on_mount(self) -> None: self.query_one("#main-input").focus()

    @on(GrowingTextArea.Changed)
    def handle_changes(self, event: GrowingTextArea.Changed) -> None:
        event.text_area.styles.height = min(max(1, event.text_area.document.line_count), 10)
        self.update_autocomplete(event.text_area.text)

    def update_autocomplete(self, text: str) -> None:
        autocomplete = self.query_one("#autocomplete-list", OptionList)
        if text.startswith("/"):
            filtered = [(c.name, c.description) for c in self.command_manager.commands.values() if c.name.startswith(text)]
            if filtered:
                autocomplete.clear_options()
                for name, desc in filtered: autocomplete.add_option(Option(f"{name.ljust(15)} {desc}"))
                autocomplete.highlighted = 0; autocomplete.set_class(True, "visible"); return
        autocomplete.set_class(False, "visible")

    def add_to_history(self, text: str, is_user: bool = False):
        history = self.query_one("#history-container")
        if is_user: history.mount(Static(f"> {text}", classes="user-msg"))
        else: history.mount(Markdown(text, classes="ai-msg"))
        history.scroll_end(animate=False)

    @on(GrowingTextArea.Submitted)
    async def handle_submission(self, event: GrowingTextArea.Submitted) -> None:
        user_input = event.text
        self.add_to_history(user_input, is_user=True)
        if user_input.startswith("/"):
            await self.process_command(user_input)
        else:
            self.run_worker(self.stream_agent_response(user_input))
        self.query_one("#main-input").focus()

    async def stream_agent_response(self, user_input: str):
        """Worker to consume events from the agent and update the UI."""
        history = self.query_one("#history-container")
        
        # Create a container for the agent's progress
        task_label = Label("Thinking...", id="task-label")
        progress = Horizontal(
            DNASpinner(),
            task_label,
            classes="agent-spinner",
            id="agent-progress"
        )
        progress.styles.height = 1
        progress.styles.margin = (1, 0)
        history.mount(progress)
        history.scroll_end(animate=False)
        
        markdown_widget = None
        full_text = ""

        async for event in self.agent.ask(user_input):
            if isinstance(event, AgentThinking):
                task_label.update(event.message)
            
            elif isinstance(event, AgentToolStart):
                task_label.update(f"Running tool: [bold cyan]{event.tool_name}[/]")
            
            elif isinstance(event, AgentStreamChunk):
                # If we're starting to stream, remove the spinner and create the Markdown widget
                if not markdown_widget:
                    progress.remove()
                    markdown_widget = Markdown("", classes="ai-msg")
                    history.mount(markdown_widget)
                
                full_text += event.text
                markdown_widget.update(full_text)
                history.scroll_end(animate=False)
            
            elif isinstance(event, AgentComplete):
                # If we never got a stream (e.g. only tool calls), remove progress
                if "agent-progress" in [c.id for c in history.children]:
                    progress.remove()
                history.scroll_end(animate=False)

    async def process_command(self, cmd_str: str):
        parts = cmd_str.split()
        name = parts[0].lower()
        args = parts[1:]

        if name == "/help":
            self.add_to_history(self.command_manager.get_all_help())
            return

        cmd = self.command_manager.get_command(name)
        if not cmd:
            self.add_to_history(f"Unknown command: {name}")
            return

        if cmd.requires_permission and not self.permission_manager.is_tool_approved(name):
            self.push_screen(PermissionScreen(name), lambda approved: self.handle_command_auth(approved, cmd, args))
        else:
            self.run_worker(cmd.execute(self, args))

    async def handle_command_auth(self, approved: bool, cmd, args):
        if approved:
            self.permission_manager.approve_tool(cmd.name)
            self.run_worker(cmd.execute(self, args))
        else:
            self.add_to_history(f"Permission denied for {cmd.name}.")

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected):
        if event.row_key is not None:
            path = Path(str(event.row_key))
            if path.is_file():
                cmd = self.command_manager.get_command("/head")
                if cmd: self.run_worker(cmd.execute(self, [str(path), "20"]))

    @on(DirectoryTree.FileSelected)
    def handle_file_selected(self, event: DirectoryTree.FileSelected):
        cmd = self.command_manager.get_command("/head")
        if cmd: self.run_worker(cmd.execute(self, [str(event.path), "20"]))

    @on(OptionList.OptionSelected)
    def handle_selection(self, event: OptionList.OptionSelected):
        if event.option_list.id == "autocomplete-list": return
        list_id = event.option_list.id; choice = str(event.option.prompt)
        if list_id and list_id.startswith("opt-q"):
            self.survey_answers[list_id] = choice
            tabs = self.query_one("#survey-tabs", TabbedContent)
            if list_id == "opt-q1": tabs.active = "q2"; self.call_after_refresh(lambda: self.query_one("#opt-q2", OptionList).focus())
            else: self.add_to_history("Survey complete."); self.cancel_interaction()
        else:
            self.add_to_history(f"Selected: **{choice}**")
            self.cancel_interaction()

    @on(events.DescendantBlur)
    def handle_descendant_blur(self, event: events.DescendantBlur):
        if "visible" in self.query_one("#interaction-container").classes: self.set_timer(0.1, self.check_focus_loss)

    def check_focus_loss(self):
        try:
            container = self.query_one("#interaction-container")
            if "visible" in container.classes and not any(w.has_focus for w in container.query("*")): self.cancel_interaction()
        except: pass

    def action_cancel_interaction(self):
        if "visible" in self.query_one("#interaction-container").classes: self.cancel_interaction()

    def cancel_interaction(self):
        container = self.query_one("#interaction-container")
        container.remove_class("visible"); container.query("*").remove()
        self.query_one("#main-input").focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            try:
                tabs = self.query_one("#survey-tabs", TabbedContent)
                if tabs.visible: event.prevent_default(); self.action_next_tab()
            except: pass

    def action_next_tab(self):
        try:
            tabs = self.query_one("#survey-tabs", TabbedContent)
            tabs.active = "q2" if tabs.active == "q1" else "q1"
            self.query_one(f"#opt-{tabs.active}", OptionList).focus()
        except: pass

    def action_prev_tab(self): self.action_next_tab()

    def action_double_ctrl_d(self):
        if time.time() - self.last_ctrl_d_time < 1.0: self.exit()
        else: self.last_ctrl_d_time = time.time(); self.notify("Press Ctrl+D again to exit", timeout=1)

def main():
    ChatApp().run()

if __name__ == "__main__":
    main()
