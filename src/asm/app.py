"""Main Textual application."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from asm.i18n import t
from asm.screens.backups import BackupsPane
from asm.screens.codex_sessions import CodexSessionsPane
from asm.screens.dashboard import DashboardPane
from asm.screens.debug_todos import DebugTodosPane
from asm.screens.file_history import FileHistoryPane
from asm.screens.migrate import MigratePane
from asm.screens.projects import ProjectsPane


class CCTuiApp(App):
    """asm — Claude Code & Codex session/data manager TUI."""

    TITLE = "asm"
    SUB_TITLE = "Claude Code & Codex session manager"

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
        Binding("tab", "tab_nav_next", "Next", show=False, priority=True),
        Binding("shift+tab", "tab_nav_prev", "Previous", show=False, priority=True),
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("f1", "tab('tab-dashboard')", "Dashboard"),
        Binding("f2", "tab('tab-projects')", "Projects"),
        Binding("f3", "tab('tab-file-history')", "File History"),
        Binding("f4", "tab('tab-debug-todos')", "Debug/Todos"),
        Binding("f5", "tab('tab-migrate')", "Migrate"),
        Binding("f6", "tab('tab-backups')", "Backups"),
    ]

    def __init__(self, target_path: str | None = None, source: str = "all", **kwargs):
        super().__init__(**kwargs)
        if target_path:
            self.target_path = str(Path(target_path).resolve())
        else:
            self.target_path = None
        # Initial dashboard source filter (all | claude | codex). Both sources
        # are always loaded; this only sets the dashboard's starting view.
        self.source = source

    @property
    def target_encoded(self) -> str | None:
        """Encoded project dir name for the target path."""
        if self.target_path:
            from asm.models import encode_path
            return encode_path(self.target_path)
        return None

    def compose(self) -> ComposeResult:
        if self.target_path:
            self.sub_title = f"Project: {self.target_path}"
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane(t("tab.dashboard"), id="tab-dashboard"):
                yield DashboardPane()
            # Claude-specific management tabs (operate on ~/.claude).
            with TabPane(t("tab.projects"), id="tab-projects"):
                yield ProjectsPane()
            with TabPane(t("tab.file_history"), id="tab-file-history"):
                yield FileHistoryPane()
            with TabPane(t("tab.debug_todos"), id="tab-debug-todos"):
                yield DebugTodosPane()
            with TabPane(t("tab.migrate"), id="tab-migrate"):
                yield MigratePane()
            # Codex sessions (operate on ~/.codex); only shown when present.
            if self._codex_available():
                with TabPane(t("tab.codex_sessions"), id="tab-codex-sessions"):
                    yield CodexSessionsPane()
            with TabPane(t("tab.backups"), id="tab-backups"):
                yield BackupsPane()
        yield Footer()

    @staticmethod
    def _codex_available() -> bool:
        from asm.services import codex_data
        return codex_data.is_available()

    def action_tab(self, tab_id: str) -> None:
        """Switch to a specific tab by ID (ignored if the tab isn't present)."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            tabs.get_pane(tab_id)
        except Exception:
            return
        tabs.active = tab_id

    def action_tab_nav_next(self) -> None:
        """Handle Tab navigation, with dashboard period cycling override."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active == "tab-dashboard":
            self.query_one("DashboardPane").action_period_next()
            return
        self.screen.focus_next()

    def action_tab_nav_prev(self) -> None:
        """Handle reverse Tab navigation, with dashboard period cycling override."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active == "tab-dashboard":
            self.query_one("DashboardPane").action_period_prev()
            return
        self.screen.focus_previous()

    def action_refresh(self) -> None:
        """Refresh all panes that have refresh_data."""
        from asm.services import codex_data
        codex_data.refresh()
        for pane in self.query(
            "DashboardPane, ProjectsPane, CodexSessionsPane, FileHistoryPane, "
            "DebugTodosPane, MigratePane, BackupsPane"
        ):
            if hasattr(pane, "refresh_data"):
                pane.refresh_data()
        self.notify(t("app.refreshed"))
