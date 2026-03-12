"""Debug files and Todos management screen."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_debug_files, get_todos
from cc_tui.services.cleaner import trash_debug_file, trash_todo_file


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class DebugTodosPane(Container):
    """View and manage debug files and todos."""

    CSS = """
    DebugTodosPane {
        height: 1fr;
        padding: 1;
    }
    .dt-section {
        height: 1fr;
        margin-bottom: 1;
    }
    .section-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="dt-section"):
            yield Static("Debug Files", classes="section-title")
            yield Button("Trash Selected Debug", variant="error", id="btn-trash-debug")
            yield DataTable(id="debug-table")
        with Vertical(classes="dt-section"):
            yield Static("Todo Files", classes="section-title")
            yield Button("Trash Selected Todo", variant="error", id="btn-trash-todo")
            yield DataTable(id="todo-table")

    def on_mount(self) -> None:
        dt = self.query_one("#debug-table", DataTable)
        dt.cursor_type = "row"
        dt.zebra_stripes = True
        dt.add_columns("Name", "Size")

        tt = self.query_one("#todo-table", DataTable)
        tt.cursor_type = "row"
        tt.zebra_stripes = True
        tt.add_columns("Name", "Size")

        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        debug = get_debug_files()
        todos = get_todos()
        self.app.call_from_thread(self._update, debug, todos)

    def _update(self, debug, todos) -> None:
        dt = self.query_one("#debug-table", DataTable)
        dt.clear()
        for d in debug:
            dt.add_row(d.name, _format_bytes(d.size_bytes), key=d.name)

        tt = self.query_one("#todo-table", DataTable)
        tt.clear()
        for t in todos:
            tt.add_row(t.name, _format_bytes(t.size_bytes), key=t.name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-debug":
            table = self.query_one("#debug-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                name = row_key.value
                self.app.push_screen(
                    ConfirmScreen(f"Move debug '{name}' to trash?"),
                    callback=lambda ok, n=name: self._trash_debug(n) if ok else None,
                )
        elif event.button.id == "btn-trash-todo":
            table = self.query_one("#todo-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                name = row_key.value
                self.app.push_screen(
                    ConfirmScreen(f"Move todo '{name}' to trash?"),
                    callback=lambda ok, n=name: self._trash_todo(n) if ok else None,
                )

    def _trash_debug(self, name: str) -> None:
        if trash_debug_file(name):
            self.app.notify(f"Trashed debug: {name}")
            self.refresh_data()
        else:
            self.app.notify("Failed", severity="error")

    def _trash_todo(self, name: str) -> None:
        if trash_todo_file(name):
            self.app.notify(f"Trashed todo: {name}")
            self.refresh_data()
        else:
            self.app.notify("Failed", severity="error")
