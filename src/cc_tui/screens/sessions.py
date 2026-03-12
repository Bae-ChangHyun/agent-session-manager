"""Sessions management screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_session_details, get_session_messages, get_sessions
from cc_tui.services.cleaner import trash_session


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class SessionsPane(Container):
    """View and manage session data."""

    CSS = """
    SessionsPane {
        height: 1fr;
        padding: 1;
    }
    #sessions-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #sessions-layout {
        height: 1fr;
    }
    #sessions-left {
        width: 2fr;
        height: 1fr;
    }
    #sessions-right {
        width: 1fr;
        height: 1fr;
        border-left: tall $primary;
        padding-left: 1;
    }
    #sessions-table {
        height: 1fr;
    }
    #session-detail-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #session-messages {
        height: 1fr;
    }
    .msg-user {
        color: $success;
        margin-bottom: 1;
    }
    .msg-assistant {
        color: $secondary;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Session data from ~/.claude/projects/. Select a session to preview messages.",
            id="sessions-info",
        )
        yield Button("Trash Selected Session", variant="error", id="btn-trash-session")
        with Horizontal(id="sessions-layout"):
            with Vertical(id="sessions-left"):
                yield DataTable(id="sessions-table")
            with Vertical(id="sessions-right"):
                yield Static("Session Preview", id="session-detail-title")
                yield VerticalScroll(Static("Select a session to preview", id="session-preview"), id="session-messages")

    def on_mount(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Directory", "Size", "Files", "Envs", "Orphaned")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_sessions, thread=True)

    def _load_sessions(self) -> None:
        sessions = get_sessions()
        self.app.call_from_thread(self._update_table, sessions)

    def _update_table(self, sessions) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear()
        self._sessions = {s.dir_name: s for s in sessions}
        for s in sessions:
            orphaned = "[red]Yes[/]" if s.is_orphaned else "[green]No[/]"
            table.add_row(
                s.dir_name,
                _format_bytes(s.size_bytes),
                str(s.file_count),
                str(len(s.session_env_dirs)),
                orphaned,
                key=s.dir_name,
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self.run_worker(lambda: self._load_preview(event.row_key.value), thread=True)

    def _load_preview(self, dir_name: str) -> None:
        """Load session messages for preview."""
        details = get_session_details(None)
        # Find sessions in this directory
        matching = [d for d in details if d.project_dir == dir_name or dir_name in d.project_dir]
        if matching:
            session = matching[0]
            messages = get_session_messages(session.session_id, limit=20)
            self.app.call_from_thread(self._update_preview, session, messages)
        else:
            # Try direct JSONL parsing for this directory
            from pathlib import Path
            from cc_tui.models import PROJECTS_DIR
            session_dir = PROJECTS_DIR / dir_name
            jsonl_files = list(session_dir.glob("*.jsonl")) if session_dir.exists() else []
            if jsonl_files:
                session_id = jsonl_files[0].stem
                messages = get_session_messages(session_id, limit=20)
                self.app.call_from_thread(self._update_preview_simple, dir_name, messages)
            else:
                self.app.call_from_thread(self._update_preview_empty, dir_name)

    def _update_preview(self, session, messages) -> None:
        preview = self.query_one("#session-preview", Static)
        title = self.query_one("#session-detail-title", Static)
        title.update(f"Session: {session.summary[:50] or session.session_id[:12]}")
        if messages:
            lines = []
            for m in messages[-10:]:
                role = "User" if m["type"] == "user" else "Assistant"
                content = m["content"][:200].replace("\n", " ")
                color = "green" if m["type"] == "user" else "cyan"
                lines.append(f"[{color}]{role}:[/] {content}")
            preview.update("\n\n".join(lines))
        else:
            preview.update("No messages found")

    def _update_preview_simple(self, dir_name, messages) -> None:
        title = self.query_one("#session-detail-title", Static)
        title.update(f"Session: {dir_name[:40]}")
        preview = self.query_one("#session-preview", Static)
        if messages:
            lines = []
            for m in messages[-10:]:
                role = "User" if m["type"] == "user" else "Assistant"
                content = m["content"][:200].replace("\n", " ")
                color = "green" if m["type"] == "user" else "cyan"
                lines.append(f"[{color}]{role}:[/] {content}")
            preview.update("\n\n".join(lines))
        else:
            preview.update("No messages found")

    def _update_preview_empty(self, dir_name) -> None:
        title = self.query_one("#session-detail-title", Static)
        title.update(f"Session: {dir_name[:40]}")
        preview = self.query_one("#session-preview", Static)
        preview.update("No session files found in this directory")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-session":
            table = self.query_one("#sessions-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                dir_name = row_key.value
                self.app.push_screen(
                    ConfirmScreen(f"Move '{dir_name}' to trash?"),
                    callback=lambda ok: self._do_trash(dir_name) if ok else None,
                )

    def _do_trash(self, dir_name: str) -> None:
        if trash_session(dir_name):
            self.app.notify(f"Trashed: {dir_name}")
            self.refresh_data()
        else:
            self.app.notify("Failed to trash", severity="error")
