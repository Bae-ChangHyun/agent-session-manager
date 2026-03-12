"""Main Textual application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, TabbedContent, TabPane

from cc_tui.screens.backups import BackupsPane
from cc_tui.screens.dashboard import DashboardPane
from cc_tui.screens.debug_todos import DebugTodosPane
from cc_tui.screens.file_history import FileHistoryPane
from cc_tui.screens.migrate import MigratePane
from cc_tui.screens.orphaned import OrphanedPane
from cc_tui.screens.projects import ProjectsPane
from cc_tui.screens.sessions import SessionsPane


class CCTuiApp(App):
    """Claude Code Session Manager TUI."""

    TITLE = "CC-TUI"
    SUB_TITLE = "Claude Code Session Manager"

    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    #main-tabs {
        height: 1fr;
    }
    .pane-container {
        height: 1fr;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, target_path: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.target_path = target_path

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield DashboardPane()
            with TabPane("Projects", id="tab-projects"):
                yield ProjectsPane()
            with TabPane("Sessions", id="tab-sessions"):
                yield SessionsPane()
            with TabPane("File History", id="tab-file-history"):
                yield FileHistoryPane()
            with TabPane("Orphaned", id="tab-orphaned"):
                yield OrphanedPane()
            with TabPane("Debug/Todos", id="tab-debug-todos"):
                yield DebugTodosPane()
            with TabPane("Migrate", id="tab-migrate"):
                yield MigratePane()
            with TabPane("Backups", id="tab-backups"):
                yield BackupsPane()
        yield Footer()

    def action_refresh(self) -> None:
        """Refresh all panes."""
        for pane in self.query("DashboardPane, ProjectsPane, SessionsPane, OrphanedPane"):
            if hasattr(pane, "refresh_data"):
                pane.refresh_data()
        self.notify("Refreshed")
