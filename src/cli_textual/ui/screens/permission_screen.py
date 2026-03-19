from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Label, Button
from textual.screen import ModalScreen

class PermissionScreen(ModalScreen[bool]):
    """A modal screen to ask for tool execution permission."""
    
    DEFAULT_CSS = """
    PermissionScreen {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    #question {
        margin-bottom: 1;
        content-align: center middle;
    }
    .buttons {
        height: 3;
        align: center middle;
    }
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(f"Authorize tool: [bold cyan]{self.tool_name}[/]", id="question")
            yield Label("This tool wants to run on your system. Allow it?", id="sub-question")
            with Horizontal(classes="buttons"):
                yield Button("Allow", variant="success", id="allow")
                yield Button("Deny", variant="error", id="deny")

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed):
        if event.button.id == "allow":
            self.dismiss(True)
        else:
            self.dismiss(False)
