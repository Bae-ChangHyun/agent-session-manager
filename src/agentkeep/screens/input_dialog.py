"""Simple text input dialog modal screen."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from agentkeep.i18n import t


class InputDialog(ModalScreen[str | None]):
    """A modal dialog with a text input field."""

    CSS = """
    InputDialog {
        align: center middle;
    }
    #input-dialog {
        padding: 1 2;
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
    }
    #input-title {
        height: auto;
        margin-bottom: 1;
        text-style: bold;
    }
    #input-label {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #input-field {
        margin-bottom: 1;
    }
    #input-hint {
        height: auto;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, label: str, placeholder: str = "", **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._label = label
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Static(self._title, id="input-title")
            yield Static(self._label, id="input-label")
            yield Input(placeholder=self._placeholder, id="input-field")
            yield Static(
                f"[dim]Enter={t('confirm.yes')}  Esc={t('confirm.no')}[/]",
                id="input-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
