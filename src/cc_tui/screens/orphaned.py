"""Orphaned data detection and cleanup screen."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_debug_files, get_file_history, get_sessions, get_todos
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
    .section-label {
        text-style: bold;
        color: $warning;
    }
    .section-desc {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Orphaned[/] - .claude.json에 매칭 프로젝트가 없는 잔여 데이터\n"
            "[dim]프로젝트를 삭제/이동한 뒤 남은 데이터입니다. 모두 휴지통으로 이동되며 복구 가능합니다.[/]",
            id="orphaned-info",
        )

        # Section 1: Orphaned Sessions
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="session-header")
            yield Button("Trash All Orphaned Sessions", variant="error", id="btn-trash-orphaned-sessions")
            yield DataTable(id="orphaned-sessions-table")

        # Section 2: Orphaned File History
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="fh-header")
            yield Button("Trash All Orphaned File History", variant="error", id="btn-trash-orphaned-fh")
            yield DataTable(id="orphaned-fh-table")

        # Section 3: Orphaned Debug
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="debug-header")
            yield Button("Trash All Orphaned Debug", variant="error", id="btn-trash-orphaned-debug")
            yield DataTable(id="orphaned-debug-table")

        # Section 4: Orphaned Todos
        with Vertical(classes="orphaned-section"):
            yield Static("", classes="section-header", id="todo-header")
            yield Button("Trash All Orphaned Todos", variant="error", id="btn-trash-orphaned-todos")
            yield DataTable(id="orphaned-todos-table")

    def on_mount(self) -> None:
        for tid in ("orphaned-sessions-table", "orphaned-fh-table", "orphaned-debug-table", "orphaned-todos-table"):
            t = self.query_one(f"#{tid}", DataTable)
            t.cursor_type = "row"
            t.zebra_stripes = True

        self.query_one("#orphaned-sessions-table", DataTable).add_columns("Session Directory", "Files")
        self.query_one("#orphaned-fh-table", DataTable).add_columns("File History Directory")
        self.query_one("#orphaned-debug-table", DataTable).add_columns("Debug File", "Size")
        self.query_one("#orphaned-todos-table", DataTable).add_columns("Todo File", "Size")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        sessions = [s for s in get_sessions() if s.is_orphaned]
        fh = [f for f in get_file_history() if f.is_orphaned]
        debug = [d for d in get_debug_files() if d.is_orphaned]
        todos = [t for t in get_todos() if t.is_orphaned]
        self.app.call_from_thread(self._update, sessions, fh, debug, todos)

    def _update(self, sessions, fh, debug, todos) -> None:
        self._orphaned_sessions = sessions
        self._orphaned_fh = fh
        self._orphaned_debug = debug
        self._orphaned_todos = todos

        # Update headers with counts
        self.query_one("#session-header", Static).update(
            f"[bold yellow]Orphaned Sessions[/]  [dim](.claude.json에 없는 세션 디렉토리)[/]  —  [bold]{len(sessions)}[/]개"
        )
        self.query_one("#fh-header", Static).update(
            f"[bold yellow]Orphaned File History[/]  [dim](프로젝트 없는 파일 버전 히스토리)[/]  —  [bold]{len(fh)}[/]개"
        )
        self.query_one("#debug-header", Static).update(
            f"[bold yellow]Orphaned Debug[/]  [dim](세션 없는 디버그 로그)[/]  —  [bold]{len(debug)}[/]개"
        )
        self.query_one("#todo-header", Static).update(
            f"[bold yellow]Orphaned Todos[/]  [dim](세션 없는 할일 메모)[/]  —  [bold]{len(todos)}[/]개"
        )

        # Populate tables
        st = self.query_one("#orphaned-sessions-table", DataTable)
        st.clear()
        for s in sessions:
            st.add_row(s.dir_name, str(s.file_count), key=s.dir_name)

        ft = self.query_one("#orphaned-fh-table", DataTable)
        ft.clear()
        for f in fh:
            ft.add_row(f.dir_name, key=f.dir_name)

        dt = self.query_one("#orphaned-debug-table", DataTable)
        dt.clear()
        for d in debug[:100]:  # Limit display
            dt.add_row(d.name, _fmt(d.size_bytes), key=d.name)

        tt = self.query_one("#orphaned-todos-table", DataTable)
        tt.clear()
        for t in todos[:100]:
            tt.add_row(t.name, _fmt(t.size_bytes), key=t.name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "btn-trash-orphaned-sessions": (self._orphaned_sessions, "sessions", self._trash_sessions),
            "btn-trash-orphaned-fh": (self._orphaned_fh, "file history", self._trash_fh),
            "btn-trash-orphaned-debug": (self._orphaned_debug, "debug files", self._trash_debug),
            "btn-trash-orphaned-todos": (self._orphaned_todos, "todo files", self._trash_todos),
        }
        handler = handlers.get(event.button.id)
        if handler:
            items, label, action = handler
            count = len(items)
            if count == 0:
                self.app.notify(f"No orphaned {label}")
                return
            self.app.push_screen(
                ConfirmScreen(f"Move {count} orphaned {label} to trash?"),
                callback=lambda ok: action() if ok else None,
            )

    def _trash_sessions(self) -> None:
        ok = sum(1 for s in self._orphaned_sessions if trash_session(s.dir_name))
        self.app.notify(f"Trashed {ok}/{len(self._orphaned_sessions)} sessions")
        self.refresh_data()

    def _trash_fh(self) -> None:
        ok = sum(1 for f in self._orphaned_fh if trash_file_history(f.dir_name))
        self.app.notify(f"Trashed {ok}/{len(self._orphaned_fh)} file history")
        self.refresh_data()

    def _trash_debug(self) -> None:
        ok = sum(1 for d in self._orphaned_debug if trash_debug_file(d.name))
        self.app.notify(f"Trashed {ok}/{len(self._orphaned_debug)} debug files")
        self.refresh_data()

    def _trash_todos(self) -> None:
        ok = sum(1 for t in self._orphaned_todos if trash_todo_file(t.name))
        self.app.notify(f"Trashed {ok}/{len(self._orphaned_todos)} todos")
        self.refresh_data()
