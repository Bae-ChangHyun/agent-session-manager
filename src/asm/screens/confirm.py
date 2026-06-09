"""Confirmation dialog modal screen."""

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from asm.i18n import t


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
        ("enter", "select_focused", "Enter"),
        ("escape", "cancel", "Cancel"),
        ("left", "focus_left", "Left"),
        ("right", "focus_right", "Right"),
    ]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        # Default focus on "No" — these dialogs gate destructive actions, so an
        # accidental Enter shouldn't confirm a delete.
        self._focused_idx = 1  # 0=yes, 1=no

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self.message, id="confirm-question")
            yield Static("", id="confirm-actions")

    def on_mount(self) -> None:
        self._render_bar()

    def _render_bar(self) -> None:
        yes_text = f" {t('confirm.yes')} "
        no_text = f" {t('confirm.no')} "
        yes_w = cell_len(yes_text)
        no_w = cell_len(no_text)
        gap = 4
        self._action_map = [
            (0, yes_w, "yes"),
            (yes_w + gap, yes_w + gap + no_w, "no"),
        ]

        if self._focused_idx == 0:
            yes_part = f"[bold white on #ba3c5b]{yes_text}[/]"
            no_part = f"[bold on #555555]{no_text}[/]"
        else:
            yes_part = f"[bold on #555555]{yes_text}[/]"
            no_part = f"[bold white on #ba3c5b]{no_text}[/]"

        self.query_one("#confirm-actions", Static).update(
            f"{yes_part}    {no_part}"
        )

    def on_click(self, event) -> None:
        widget = event.widget
        if getattr(widget, "id", "") != "confirm-actions":
            return
        # content-align: center shifts rendered text; adjust x for centering offset
        total_text_w = self._action_map[-1][1]  # end of last entry
        widget_w = widget.size.width
        offset = max(0, (widget_w - total_text_w) // 2)
        x = event.x - offset
        for start, end, action in self._action_map:
            if start <= x < end:
                self.dismiss(action == "yes")
                return
        # Click was on the actions bar but outside buttons — ignore (don't dismiss)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_select_focused(self) -> None:
        self.dismiss(self._focused_idx == 0)

    def action_focus_left(self) -> None:
        self._focused_idx = 0
        self._render_bar()

    def action_focus_right(self) -> None:
        self._focused_idx = 1
        self._render_bar()
