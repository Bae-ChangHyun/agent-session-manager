"""Orphaned data detection and cleanup screen."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, DataTable, Static

from cc_tui.models import decode_path_hint
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_debug_files, get_file_history, get_sessions, get_todos
from cc_tui.i18n import t
from cc_tui.services.cleaner import trash_debug_file, trash_file_history, trash_session, trash_todo_file


def _fmt(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class OrphanedPane(Container):
    CSS = """
    OrphanedPane {
        height: 1fr;
        padding: 1;
    }
    #orphaned-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    .orphaned-section {
        height: 1fr;
        min-height: 8;
        margin-bottom: 1;
    }
    .section-header {
        height: auto;
        margin-bottom: 0;
    }
    .trash-btn {
        width: auto;
        margin-top: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            t("orph.info"),
            id="orphaned-info",
        )

        # Section 1: Orphaned Session Dirs
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="session-header")
            yield Button("Trash Selected Session Dir", variant="warning", id="btn-trash-one-session", classes="trash-btn")
            yield DataTable(id="orphaned-sessions-table")

        # Section 2: Orphaned File History
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="fh-header")
            yield Button("Trash Selected File History", variant="warning", id="btn-trash-one-fh", classes="trash-btn")
            yield DataTable(id="orphaned-fh-table")

        # Section 3: Orphaned Debug
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="debug-header")
            yield Button("Trash Selected Debug", variant="warning", id="btn-trash-one-debug", classes="trash-btn")
            yield DataTable(id="orphaned-debug-table")

        # Section 4: Orphaned Todos
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="todo-header")
            yield Button("Trash Selected Todo", variant="warning", id="btn-trash-one-todo", classes="trash-btn")
            yield DataTable(id="orphaned-todos-table")

    def on_mount(self) -> None:
        for tid in ("orphaned-sessions-table", "orphaned-fh-table", "orphaned-debug-table", "orphaned-todos-table"):
            t = self.query_one(f"#{tid}", DataTable)
            t.cursor_type = "row"
            t.zebra_stripes = True

        self.query_one("#orphaned-sessions-table", DataTable).add_columns("Project Path (decoded)", "Session Files")
        self.query_one("#orphaned-fh-table", DataTable).add_columns("Path (decoded)")
        self.query_one("#orphaned-debug-table", DataTable).add_columns("Debug File", "Size")
        self.query_one("#orphaned-todos-table", DataTable).add_columns("Todo File", "Size")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        sessions = [s for s in get_sessions() if s.is_orphaned]
        fh = [f for f in get_file_history() if f.is_orphaned]
        debug = [d for d in get_debug_files() if d.is_orphaned]
        todos = [td for td in get_todos() if td.is_orphaned]
        self.app.call_from_thread(self._update, sessions, fh, debug, todos)

    def _update(self, sessions, fh, debug, todos) -> None:
        self._orphaned_sessions = {s.dir_name: s for s in sessions}
        self._orphaned_fh = {f.dir_name: f for f in fh}
        self._orphaned_debug = {d.name: d for d in debug}
        self._orphaned_todos = {td.name: td for td in todos}

        total_session_files = sum(s.file_count for s in sessions)

        # Update headers
        self.query_one("#session-header", Static).update(
            f"{t('orph.session_header')}\n"
            f"[bold]{len(sessions)}[/]  |  [bold]{total_session_files}[/] files"
        )
        self.query_one("#fh-header", Static).update(
            f"{t('orph.fh_header')}  —  [bold]{len(fh)}[/]"
        )
        self.query_one("#debug-header", Static).update(
            f"{t('orph.debug_header')}  —  [bold]{len(debug)}[/]"
        )
        self.query_one("#todo-header", Static).update(
            f"{t('orph.todo_header')}  —  [bold]{len(todos)}[/]"
        )

        # Sessions table - show decoded path + file count
        st = self.query_one("#orphaned-sessions-table", DataTable)
        st.clear()
        for s in sessions:
            path_hint = decode_path_hint(s.dir_name)
            st.add_row(path_hint, f"{s.file_count} files", key=s.dir_name)

        ft = self.query_one("#orphaned-fh-table", DataTable)
        ft.clear()
        for f in fh:
            ft.add_row(decode_path_hint(f.dir_name), key=f.dir_name)

        dt = self.query_one("#orphaned-debug-table", DataTable)
        dt.clear()
        for d in debug[:100]:
            dt.add_row(d.name, _fmt(d.size_bytes), key=d.name)

        tt = self.query_one("#orphaned-todos-table", DataTable)
        tt.clear()
        for td in todos[:100]:
            tt.add_row(td.name, _fmt(td.size_bytes), key=td.name)

    def _get_selected_row_key(self, table_id: str) -> str | None:
        table = self.query_one(f"#{table_id}", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key = list(table.rows.keys())[table.cursor_row]
            return row_key.value
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-one-session":
            key = self._get_selected_row_key("orphaned-sessions-table")
            if not key or key not in self._orphaned_sessions:
                self.app.notify(t("orph.select_first"))
                return
            s = self._orphaned_sessions[key]
            path_hint = decode_path_hint(s.dir_name)
            self.app.push_screen(
                ConfirmScreen(
                    t("orph.confirm_session", path=path_hint, count=s.file_count)
                ),
                callback=lambda ok, n=s.dir_name: self._trash_one_session(n) if ok else None,
            )

        elif event.button.id == "btn-trash-one-fh":
            key = self._get_selected_row_key("orphaned-fh-table")
            if not key or key not in self._orphaned_fh:
                self.app.notify(t("orph.select_first"))
                return
            self.app.push_screen(
                ConfirmScreen(
                    t("orph.confirm_fh", name=decode_path_hint(key))
                ),
                callback=lambda ok, n=key: self._trash_one_fh(n) if ok else None,
            )

        elif event.button.id == "btn-trash-one-debug":
            key = self._get_selected_row_key("orphaned-debug-table")
            if not key or key not in self._orphaned_debug:
                self.app.notify(t("orph.select_first"))
                return
            self.app.push_screen(
                ConfirmScreen(
                    t("orph.confirm_debug", name=key)
                ),
                callback=lambda ok, n=key: self._trash_one_debug(n) if ok else None,
            )

        elif event.button.id == "btn-trash-one-todo":
            key = self._get_selected_row_key("orphaned-todos-table")
            if not key or key not in self._orphaned_todos:
                self.app.notify(t("orph.select_first"))
                return
            self.app.push_screen(
                ConfirmScreen(
                    t("orph.confirm_todo", name=key)
                ),
                callback=lambda ok, n=key: self._trash_one_todo(n) if ok else None,
            )

    def _trash_one_session(self, dir_name: str) -> None:
        if trash_session(dir_name):
            self.app.notify(t("common.trashed", name=decode_path_hint(dir_name)))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _trash_one_fh(self, dir_name: str) -> None:
        if trash_file_history(dir_name):
            self.app.notify(t("common.trashed", name=dir_name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _trash_one_debug(self, name: str) -> None:
        if trash_debug_file(name):
            self.app.notify(t("common.trashed", name=name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _trash_one_todo(self, name: str) -> None:
        if trash_todo_file(name):
            self.app.notify(t("common.trashed", name=name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")
