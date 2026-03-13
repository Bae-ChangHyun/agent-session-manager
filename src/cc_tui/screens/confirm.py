"""Confirmation dialog modal screen."""

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from cc_tui.i18n import t


class ConfirmScreen(ModalScreen[bool]):
    """A modal confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
    }
    #confirm-question {
        height: auto;
        width: 1fr;
        content-align: center middle;
        margin-bottom: 1;
    }
    #confirm-actions {
        height: 1;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        yes_label = t("confirm.yes")
        no_label = t("confirm.no")
        yes_text = f" {yes_label} "
        no_text = f" {no_label} "
        yes_w = cell_len(yes_text)
        no_w = cell_len(no_text)
        gap = 4
        self._action_map = [
            (0, yes_w, "yes"),
            (yes_w + gap, yes_w + gap + no_w, "no"),
        ]
        bar = (
            f"[bold white on #ba3c5b]{yes_text}[/]"
            f"    "
            f"[bold white on #555555]{no_text}[/]"
        )
        with Vertical(id="confirm-dialog"):
            yield Static(self.message, id="confirm-question")
            yield Static(bar, id="confirm-actions")

    def on_click(self, event) -> None:
        if getattr(event.widget, "id", "") != "confirm-actions":
            return
        for start, end, action in self._action_map:
            if start <= event.x < end:
                self.dismiss(action == "yes")
                break

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
