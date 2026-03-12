"""Main Textual application."""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer


class CCTuiApp(App):
    """Claude Code Session Manager TUI."""

    TITLE = "CC-TUI"
    SUB_TITLE = "Claude Code Session Manager"

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, target_path: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.target_path = target_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
