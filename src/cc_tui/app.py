"""Main Textual application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from cc_tui.i18n import t
from cc_tui.screens.backups import BackupsPane
from cc_tui.screens.dashboard import DashboardPane
from cc_tui.screens.debug_todos import DebugTodosPane
from cc_tui.screens.file_history import FileHistoryPane
from cc_tui.screens.migrate import MigratePane
from cc_tui.screens.projects import ProjectsPane


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
            with TabPane(t("tab.dashboard"), id="tab-dashboard"):
                yield DashboardPane()
            with TabPane(t("tab.projects"), id="tab-projects"):
                yield ProjectsPane()
            with TabPane(t("tab.file_history"), id="tab-file-history"):
                yield FileHistoryPane()
            with TabPane(t("tab.debug_todos"), id="tab-debug-todos"):
                yield DebugTodosPane()
            with TabPane(t("tab.migrate"), id="tab-migrate"):
                yield MigratePane()
            with TabPane(t("tab.backups"), id="tab-backups"):
                yield BackupsPane()
        yield Footer()

    def action_refresh(self) -> None:
        """Refresh all panes that have refresh_data."""
        for pane in self.query("DashboardPane, ProjectsPane, FileHistoryPane, DebugTodosPane, MigratePane"):
            if hasattr(pane, "refresh_data"):
                pane.refresh_data()
        self.notify(t("app.refreshed"))
