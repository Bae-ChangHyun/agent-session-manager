"""Orphaned data detection and cleanup screen."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_file_history, get_sessions
from cc_tui.services.cleaner import trash_file_history, trash_session


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class OrphanedPane(Container):
    """View and clean orphaned data."""

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
        margin-bottom: 1;
    }
    .section-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Orphaned[/] - .claude.json에 매칭 프로젝트가 없는 고아 데이터\n"
            "[dim]프로젝트를 삭제/이동한 뒤 남은 잔여 데이터입니다. 정리해도 안전합니다.[/]",
            id="orphaned-info",
        )
        with Vertical(classes="orphaned-section"):
            yield Static("Orphaned Sessions", classes="section-title")
            yield Button("Trash All Orphaned Sessions", variant="error", id="btn-trash-orphaned-sessions")
            yield DataTable(id="orphaned-sessions-table")
        with Vertical(classes="orphaned-section"):
            yield Static("Orphaned File History", classes="section-title")
            yield Button("Trash All Orphaned File History", variant="error", id="btn-trash-orphaned-fh")
            yield DataTable(id="orphaned-fh-table")

    def on_mount(self) -> None:
        st = self.query_one("#orphaned-sessions-table", DataTable)
        st.cursor_type = "row"
        st.zebra_stripes = True
        st.add_columns("Directory", "Size", "Files")

        ft = self.query_one("#orphaned-fh-table", DataTable)
        ft.cursor_type = "row"
        ft.zebra_stripes = True
        ft.add_columns("Directory", "Size")

        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        sessions = [s for s in get_sessions() if s.is_orphaned]
        fh = [f for f in get_file_history() if f.is_orphaned]
        self.app.call_from_thread(self._update, sessions, fh)

    def _update(self, sessions, fh) -> None:
        st = self.query_one("#orphaned-sessions-table", DataTable)
        st.clear()
        self._orphaned_sessions = sessions
        for s in sessions:
            st.add_row(s.dir_name, _format_bytes(s.size_bytes), str(s.file_count), key=s.dir_name)

        ft = self.query_one("#orphaned-fh-table", DataTable)
        ft.clear()
        self._orphaned_fh = fh
        for f in fh:
            ft.add_row(f.dir_name, _format_bytes(f.size_bytes), key=f.dir_name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-orphaned-sessions":
            count = len(getattr(self, "_orphaned_sessions", []))
            if count == 0:
                self.app.notify("No orphaned sessions")
                return
            self.app.push_screen(
                ConfirmScreen(f"Move {count} orphaned sessions to trash?"),
                callback=lambda ok: self._do_trash_sessions() if ok else None,
            )
        elif event.button.id == "btn-trash-orphaned-fh":
            count = len(getattr(self, "_orphaned_fh", []))
            if count == 0:
                self.app.notify("No orphaned file history")
                return
            self.app.push_screen(
                ConfirmScreen(f"Move {count} orphaned file history entries to trash?"),
                callback=lambda ok: self._do_trash_fh() if ok else None,
            )

    def _do_trash_sessions(self) -> None:
        ok, fail = 0, 0
        for s in self._orphaned_sessions:
            if trash_session(s.dir_name):
                ok += 1
            else:
                fail += 1
        self.app.notify(f"Trashed {ok} sessions" + (f", {fail} failed" if fail else ""))
        self.refresh_data()

    def _do_trash_fh(self) -> None:
        ok, fail = 0, 0
        for f in self._orphaned_fh:
            if trash_file_history(f.dir_name):
                ok += 1
            else:
                fail += 1
        self.app.notify(f"Trashed {ok} entries" + (f", {fail} failed" if fail else ""))
        self.refresh_data()
