"""Modal editor for per-project instruction files (CLAUDE.md, AGENTS.md, …)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea


class FileEditorScreen(ModalScreen[bool]):
    """Edit (or create) a text file. Ctrl+S saves, Esc cancels.

    Returns True if the file was saved.
    """

    CSS = """
    FileEditorScreen {
        align: center middle;
    }
    #editor-dialog {
        width: 90%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    #editor-title {
        height: auto;
        text-style: bold;
        padding: 0 1;
    }
    #editor-area {
        height: 1fr;
    }
    #editor-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, path: str | Path, **kwargs):
        super().__init__(**kwargs)
        self._path = Path(path)

    def compose(self) -> ComposeResult:
        try:
            text = self._path.read_text() if self._path.exists() else ""
        except OSError as e:
            text = f"(could not read file: {e})"
        exists = self._path.exists()
        verb = "Editing" if exists else "New file"
        with Vertical(id="editor-dialog"):
            yield Static(f"[bold]{verb}:[/] {self._path}", id="editor-title")
            yield TextArea(text, id="editor-area")
            yield Static("[dim]Ctrl+S save · Esc cancel[/]", id="editor-hint")

    def on_mount(self) -> None:
        self.query_one("#editor-area", TextArea).focus()

    def action_save(self) -> None:
        text = self.query_one("#editor-area", TextArea).text
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(text)
            self.app.notify(f"Saved {self._path.name}")
            self.dismiss(True)
        except OSError as e:
            self.app.notify(f"Save failed: {e}", severity="error")

    def action_cancel(self) -> None:
        self.dismiss(False)
