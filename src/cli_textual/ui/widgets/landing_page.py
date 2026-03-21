from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Label

class LandingPage(Static):
    """The landing page shown on initial startup."""

    def compose(self) -> ComposeResult:
        with Container(id="landing-container"):
            yield Label("— TUI Framework —", id="landing-title")
            with Horizontal(id="landing-content"):
                with Container(id="landing-left"):
                    yield Static(id="landing-graphic")
                    yield Label("Modular Agentic Interface", id="landing-subtitle")
                    yield Static("Env: [cyan]dev[/]", classes="landing-info")
                    yield Static("Status: [green]ready[/]", classes="landing-info")
                
                with Container(id="landing-right"):
                    yield Label("Slash Commands", classes="landing-header")
                    yield Static("Type [cyan]/[/] for commands.", classes="landing-item")
                    
                    yield Label("Tips", classes="landing-header")
                    yield Static(r"\[[white]tab[/]]   autocomplete", classes="landing-item")
                    yield Static(r"\[[white]↑↓[/]]    navigate", classes="landing-item")
                    yield Static(r"\[[white]ctrl-c[/]] quit", classes="landing-item")
