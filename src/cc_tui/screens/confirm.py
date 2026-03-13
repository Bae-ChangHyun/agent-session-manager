"""Confirmation dialog modal screen."""

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from cc_tui.i18n import t


class ConfirmScreen(ModalScreen[bool]):
    """A modal confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: auto auto;
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
    }
    #confirm-question {
        column-span: 2;
        height: auto;
        width: 1fr;
        content-align: center middle;
        margin-bottom: 1;
    }
    Button {
        width: 100%;
    }
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(self.message, id="confirm-question"),
            Button(t("confirm.yes"), variant="error", id="confirm-yes"),
            Button(t("confirm.no"), variant="primary", id="confirm-no"),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")
