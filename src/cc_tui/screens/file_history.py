"""File history management screen."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_file_history
from cc_tui.services.cleaner import trash_file_history


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class FileHistoryPane(Container):
    """View and manage file history entries."""

    CSS = """
    FileHistoryPane {
        height: 1fr;
        padding: 1;
    }
    #fh-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #fh-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "File history entries from ~/.claude/file-history/. "
            "Version history and snapshots that can be safely cleaned.",
            id="fh-info",
        )
        yield Button("Trash Selected", variant="error", id="btn-trash-fh")
        yield DataTable(id="fh-table")

    def on_mount(self) -> None:
        table = self.query_one("#fh-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Directory", "Size", "Orphaned")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        entries = get_file_history()
        self.app.call_from_thread(self._update_table, entries)

    def _update_table(self, entries) -> None:
        table = self.query_one("#fh-table", DataTable)
        table.clear()
        for e in entries:
            orphaned = "[red]Yes[/]" if e.is_orphaned else "[green]No[/]"
            table.add_row(e.dir_name, _format_bytes(e.size_bytes), orphaned, key=e.dir_name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-fh":
            table = self.query_one("#fh-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                name = row_key.value
                self.app.push_screen(
                    ConfirmScreen(f"Move file history '{name}' to trash?"),
                    callback=lambda ok, n=name: self._do_trash(n) if ok else None,
                )

    def _do_trash(self, name: str) -> None:
        if trash_file_history(name):
            self.app.notify(f"Trashed: {name}")
            self.refresh_data()
        else:
            self.app.notify("Failed to trash", severity="error")
