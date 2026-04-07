import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Callable, List, Optional

from textual import on, events
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import (
    Header, Footer, Static, Markdown, Label, OptionList,
    TabbedContent, DirectoryTree, DataTable, Collapsible
)
from textual.widgets.option_list import Option
from textual.binding import Binding

# Core Framework Imports
from cli_textual.core.fs import FSManager
from cli_textual.core.permissions import PermissionManager
from cli_textual.core.command import CommandManager
from cli_textual.core.chat_events import (
    ChatEvent, AgentThinking, AgentToolStart, AgentToolEnd, AgentToolOutput,
    AgentStreamChunk, AgentComplete, AgentRequiresUserInput, AgentExecuteCommand,
    AgentThinkingChunk, AgentThinkingComplete,
)

# Pydantic AI Orchestrators
from cli_textual.agents.manager import run_manager_pipeline
from cli_textual.agents.observability import init_observability, is_tracing_enabled
from cli_textual.core.conversation_log import ConversationLogger, default_log_path

# UI Component Imports
from cli_textual.ui.widgets.growing_text_area import GrowingTextArea
from cli_textual.ui.widgets.dna_spinner import DNASpinner
from cli_textual.ui.screens.permission_screen import PermissionScreen
from cli_textual.ui.widgets.landing_page import LandingPage

class ChatApp(App):
    """Refactored ChatApp using modular architecture."""

    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+d", "double_ctrl_d", "Exit", show=True, priority=True),
        Binding("escape", "cancel_interaction", "Cancel", show=False),
        Binding("ctrl+n", "next_tab", "Next Tab", show=False, priority=True),
        Binding("ctrl+p", "prev_tab", "Prev Tab", show=False, priority=True),
    ]

    def __init__(
        self,
        tools: Optional[List[Callable]] = None,
        command_packages: Optional[List[str]] = None,
        model: Optional[str] = None,
        safe_mode: Optional[bool] = None,
        log: bool = False,
        log_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        system_prompt_append: Optional[str] = None,
        **kwargs,
    ):
        # Apply library overrides BEFORE the manager agent is first built.
        if model is not None:
            from cli_textual.agents.model import set_model
            set_model(model)
        import cli_textual.agents.manager as _mgr
        if safe_mode is not None:
            _mgr.SAFE_MODE = safe_mode
        if system_prompt is not None:
            _mgr.SYSTEM_PROMPT_OVERRIDE = system_prompt
        if system_prompt_append is not None:
            _mgr.SYSTEM_PROMPT_APPEND = system_prompt_append
        if tools:
            from cli_textual.tools.registry import register_tool
            for t in tools:
                register_tool(t)
        if (
            model is not None
            or safe_mode is not None
            or tools
            or system_prompt is not None
            or system_prompt_append is not None
        ):
            from cli_textual.agents.manager import _reset_agent
            _reset_agent()

        super().__init__(**kwargs)
        init_observability()
        self.session_id = str(uuid.uuid4())
        self.last_ctrl_d_time = 0
        self.survey_answers = {}
        # Allow setting default mode via environment variable
        self.chat_mode = os.getenv("CHAT_MODE", "manager") 
        self.message_history = [] # For LLM context memory
        self.interactive_input_queue = asyncio.Queue()
        self.verbose_mode = False
        self._agent_waiting_for_input = False

        # Optional append-only JSONL conversation log for debugging.
        self.conversation_log: Optional[ConversationLogger] = None
        if log or log_path is not None:
            target = Path(log_path) if log_path is not None else default_log_path(self.session_id)
            self.conversation_log = ConversationLogger(target, self.session_id)

        
        # Initialize Core Managers
        self.workspace_root = Path.cwd().resolve()
        self.fs_manager = FSManager(self.workspace_root)
        self.permission_manager = PermissionManager(self.workspace_root / ".agents" / "settings.json")
        self.command_manager = CommandManager()
        
        # Register Commands via Auto-Discovery
        self.command_manager.auto_discover("cli_textual.plugins.commands")
        for pkg in command_packages or []:
            self.command_manager.auto_discover(pkg)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="history-container")
        yield Container(id="interaction-container")
        with Container(id="bottom-dock"):
            with Horizontal(id="input-container"):
                yield Label("> ", id="prompt"); yield GrowingTextArea(id="main-input")
            yield OptionList(id="autocomplete-list")
            with Horizontal(id="status-bar"):
                yield Label("workspace (/directory)", classes="status-info")
                yield Label(f"mode: {self.chat_mode}", classes="status-info mode-info")
                from cli_textual.agents.model import get_model
                model_name = getattr(get_model(), "model_name", "test-mock")
                yield Label(f"model: {model_name}", classes="status-info model-info")
                trace_label = "[green]● langfuse[/]" if is_tracing_enabled() else "[dim]○ langfuse[/]"
                yield Label(trace_label, classes="status-info")
            yield Label(str(self.workspace_root), classes="path-info")
        yield Footer()

    def on_mount(self) -> None: 
        self.query_one("#main-input").focus()
        history = self.query_one("#history-container")
        history.mount(LandingPage())


    @on(OptionList.OptionSelected, "#mode-select-list")
    def handle_mode_selection(self, event: OptionList.OptionSelected) -> None:
        """Handle user selecting a mode from the /mode command list."""
        selection = str(event.option.prompt)
        self.chat_mode = selection
        
        # Clear UI
        interaction = self.query_one("#interaction-container")
        interaction.remove_class("visible")
        interaction.query("*").remove()
        
        # Feedback
        self.add_to_history(f"Chat mode set to: **{self.chat_mode}**")
        self.query_one(".mode-info").update(f"mode: {self.chat_mode}")
        self.query_one("#main-input").focus()

    @on(OptionList.OptionSelected, "#agent-select-tool")
    def handle_agent_selection(self, event: OptionList.OptionSelected) -> None:
        """Handle user making a choice requested by an agent tool."""
        selection = str(event.option.prompt)
        self._agent_waiting_for_input = False
        # Clear the interaction area
        interaction = self.query_one("#interaction-container")
        interaction.remove_class("visible")
        interaction.query("*").remove()

        # Log choice to history
        self.add_to_history(f"Selected: **{selection}**", is_user=True)

        # Resume the agent by pushing the selection into the queue
        if hasattr(self, "interactive_input_queue"):
            # Drain any stale entries (safety measure)
            while not self.interactive_input_queue.empty():
                self.interactive_input_queue.get_nowait()
            self.interactive_input_queue.put_nowait(selection)
        
        # Refocus main input
        self.query_one("#main-input").focus()

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
        if self.conversation_log is not None:
            if user_input.startswith("/"):
                parts = user_input.split()
                self.conversation_log.log_user_command(parts[0], parts[1:])
            else:
                self.conversation_log.log_user_message(user_input)
        if user_input.startswith("/"):
            await self.process_command(user_input)
        else:
            generator = run_manager_pipeline(user_input, self.interactive_input_queue, message_history=self.message_history, session_id=self.session_id)
            self.run_worker(self.stream_agent_response(generator))
        self.query_one("#main-input").focus()

    async def stream_agent_response(self, generator: AsyncGenerator[ChatEvent, None]):
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
        thinking_collapsible = None
        thinking_widget = None
        thinking_text = ""

        async for event in generator:
            if self.conversation_log is not None:
                self.conversation_log.log_event(event)
            if isinstance(event, AgentThinkingChunk):
                if not thinking_collapsible:
                    thinking_collapsible = Collapsible(
                        Static("", classes="thinking-content"),
                        title="Reasoning",
                        collapsed=not self.verbose_mode,
                        classes="thinking-block",
                    )
                    await history.mount(thinking_collapsible)
                    thinking_widget = thinking_collapsible.query_one(".thinking-content")
                thinking_text += event.text
                thinking_widget.update(thinking_text)
                history.scroll_end(animate=False)

            elif isinstance(event, AgentThinkingComplete):
                if thinking_widget:
                    thinking_widget.update(event.full_text)

            elif isinstance(event, AgentThinking):
                task_label.update(event.message)
            
            elif isinstance(event, AgentRequiresUserInput):
                # Pause and show the interaction UI
                self._agent_waiting_for_input = True
                interaction = self.query_one("#interaction-container")
                interaction.add_class("visible")
                interaction.query("*").remove()

                interaction.mount(Label(event.prompt))

                if event.tool_name == "/select":
                    options = OptionList(*event.options, id="agent-select-tool")
                    interaction.mount(options)
                    self.call_after_refresh(options.focus)

                history.scroll_end(animate=False)

            elif isinstance(event, AgentExecuteCommand):
                # Proactively execute a TUI command
                full_cmd = event.command_name
                if event.args:
                    full_cmd += " " + " ".join(event.args)
                await self.process_command(full_cmd)

            elif isinstance(event, AgentToolStart):
                task_label.update(f"Running tool: [bold cyan]{event.tool_name}[/]")

            elif isinstance(event, AgentToolOutput):
                # Render tool output as Markdown inside a collapsed-by-default
                # Collapsible so the chat stays scannable. Tool results are
                # often long (tables, file contents, JSON) and the user can
                # expand them on demand. Errors stay expanded so failures are
                # visible without a click.
                style_class = "tool-output-error" if event.is_error else "tool-output"
                status = "error" if event.is_error else "ok"
                title = f"{event.tool_name} ▸ {status}"
                coll = Collapsible(
                    Markdown(event.content or "", classes=style_class),
                    title=title,
                    collapsed=not event.is_error,
                    classes="tool-output-block",
                )
                await history.mount(coll)
                history.scroll_end(animate=False)

            elif isinstance(event, AgentToolEnd):
                task_label.update(f"Tool complete: [bold green]{event.tool_name}[/]")
            
            elif isinstance(event, AgentStreamChunk):
                # If we're starting to stream, remove the spinner and create the Markdown widget
                if not markdown_widget:
                    await progress.remove()
                    markdown_widget = Markdown("", classes="ai-msg")
                    await history.mount(markdown_widget)

                full_text += event.text
                await markdown_widget.update(full_text)
                history.scroll_end(animate=False)

            elif isinstance(event, AgentComplete):
                # Save new history for context memory
                if event.new_history:
                    self.message_history.extend(event.new_history)

                # If we never got a stream (e.g. only tool calls), remove progress
                if "agent-progress" in [c.id for c in history.children]:
                    await progress.remove()
                history.scroll_end(animate=False)

    async def process_command(self, cmd_str: str):
        parts = cmd_str.split()
        name = parts[0].lower()
        args = parts[1:]

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
            if self._agent_waiting_for_input:
                return
            container = self.query_one("#interaction-container")
            if "visible" in container.classes and not any(w.has_focus for w in container.query("*")):
                self.cancel_interaction()
        except: pass

    def action_cancel_interaction(self):
        if self._agent_waiting_for_input:
            return
        if "visible" in self.query_one("#interaction-container").classes:
            self.cancel_interaction()

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

    def on_unmount(self) -> None:
        if self.conversation_log is not None:
            self.conversation_log.close()

def main():
    import argparse

    parser = argparse.ArgumentParser(prog="demo-cli", description="cli-textual chat TUI")
    parser.add_argument(
        "--log",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=(
            "Record the full conversation (user input, LLM events, tool calls) "
            "to a JSONL file. With no argument, writes to "
            "~/.cli-textual/convos/<utc-timestamp>-<sid>.jsonl. Pass an explicit "
            "path to override."
        ),
    )
    args = parser.parse_args()

    log_enabled = args.log is not None
    log_path = Path(args.log) if args.log else None
    ChatApp(log=log_enabled, log_path=log_path).run()

if __name__ == "__main__":
    main()
