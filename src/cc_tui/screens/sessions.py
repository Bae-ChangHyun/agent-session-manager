"""Sessions screen - all sessions across all projects, sorted by recent."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_session_details, get_session_messages
from cc_tui.services.cleaner import trash_session


class SessionsPane(Container):
    """All sessions sorted by most recent."""

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
    #sessions-list-panel {
        width: 1fr;
        height: 1fr;
    }
    #sessions-table {
        height: 1fr;
    }
    #session-view-panel {
        width: 1fr;
        height: 1fr;
        border-left: tall $primary;
        padding: 0 1;
    }
    #session-view-header {
        height: auto;
        text-style: bold;
        margin-bottom: 1;
    }
    #session-view-scroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Sessions[/] - 전체 세션 목록 (최신순)\n"
            "[dim]모든 프로젝트의 세션을 시간순으로 표시합니다. 세션을 선택하면 대화를 볼 수 있습니다.[/]",
            id="sessions-info",
        )
        with Horizontal(id="sessions-layout"):
            with Vertical(id="sessions-list-panel"):
                yield DataTable(id="sessions-table")
            with Vertical(id="session-view-panel"):
                yield Static("", id="session-view-header")
                yield VerticalScroll(
                    Static("세션을 선택하세요", id="session-view-body"),
                    id="session-view-scroll",
                )

    def on_mount(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Date", "Project", "Summary", "Size")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        sessions = get_session_details(None)
        self.app.call_from_thread(self._update_table, sessions)

    def _update_table(self, sessions) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear()
        self._sessions = {}
        for s in sessions[:200]:  # Limit to 200 most recent
            self._sessions[s.session_id] = s
            ts = s.last_modified / 1000 if s.last_modified > 1e12 else s.last_modified
            dt = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts > 0 else "?"
            # Decode project dir name to readable form
            proj = s.project_dir.strip("-").split("-")
            proj_name = proj[-1] if proj else "?"
            summary = (s.summary or s.session_id[:12]).replace("\n", " ")[:40]
            size = f"{s.file_size / 1024:.0f}KB"
            table.add_row(dt, proj_name, summary, size, key=s.session_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = event.row_key.value
        if session_id and session_id in self._sessions:
            s = self._sessions[session_id]
            self.run_worker(lambda: self._load_messages(s), thread=True)

    def _load_messages(self, session) -> None:
        messages = get_session_messages(session.session_id, limit=50)
        self.app.call_from_thread(self._show_messages, session, messages)

    def _show_messages(self, session, messages) -> None:
        header = self.query_one("#session-view-header", Static)
        body = self.query_one("#session-view-body", Static)

        ts = session.last_modified / 1000 if session.last_modified > 1e12 else session.last_modified
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts > 0 else "?"
        header.update(f"[bold]{dt}[/]  {session.session_id[:16]}...")

        if not messages:
            body.update("[dim]No conversation messages in this session[/]")
            return

        lines = []
        for m in messages:
            content = m["content"]
            if m["type"] == "user":
                lines.append(f"[bold green]User:[/]\n{content}\n")
            else:
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"[bold cyan]Assistant:[/]\n{content}\n")
        body.update("\n".join(lines))
