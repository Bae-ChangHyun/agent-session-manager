"""Dashboard screen showing overall statistics."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static
from textual.worker import Worker, get_current_worker

from cc_tui.services.claude_data import get_stats


def _format_bytes(size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class StatCard(Static):
    """A card displaying a single statistic."""

    CSS = """
    StatCard {
        width: 1fr;
        height: 7;
        border: round $primary;
        padding: 1 2;
        content-align: center middle;
        text-align: center;
        margin: 0 1;
    }
    StatCard.warning {
        border: round $warning;
    }
    """


class DashboardPane(Container):
    """Dashboard with overall statistics."""

    CSS = """
    DashboardPane {
        height: 1fr;
        padding: 1;
    }
    .stat-row {
        height: auto;
        margin-bottom: 1;
    }
    #dashboard-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        width: 100%;
    }
    #loading-msg {
        text-align: center;
        width: 100%;
        margin: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Claude Code Data Overview", id="dashboard-title")
        yield Static("Loading...", id="loading-msg")
        yield Horizontal(id="row-main", classes="stat-row")
        yield Horizontal(id="row-orphaned", classes="stat-row")
        yield Horizontal(id="row-size", classes="stat-row")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_stats, thread=True)

    def _load_stats(self) -> None:
        stats = get_stats()
        self.app.call_from_thread(self._update_display, stats)

    def _update_display(self, stats) -> None:
        loading = self.query_one("#loading-msg", Static)
        loading.display = False

        row_main = self.query_one("#row-main")
        row_main.remove_children()
        row_main.mount(StatCard(f"Projects\n\n[bold]{stats.total_projects}[/]"))
        row_main.mount(StatCard(f"Sessions\n\n[bold]{stats.total_sessions}[/]"))
        row_main.mount(StatCard(f"File History\n\n[bold]{stats.total_file_history}[/]"))
        row_main.mount(StatCard(f"Debug Files\n\n[bold]{stats.total_debug}[/]"))
        row_main.mount(StatCard(f"Todos\n\n[bold]{stats.total_todos}[/]"))

        row_orphaned = self.query_one("#row-orphaned")
        row_orphaned.remove_children()
        row_orphaned.mount(
            StatCard(
                f"Orphaned Sessions\n\n[bold red]{stats.orphaned_sessions}[/]",
                classes="warning" if stats.orphaned_sessions else "",
            )
        )
        row_orphaned.mount(
            StatCard(
                f"Orphaned File History\n\n[bold red]{stats.orphaned_file_history}[/]",
                classes="warning" if stats.orphaned_file_history else "",
            )
        )
        row_orphaned.mount(
            StatCard(
                f"Orphaned Debug\n\n[bold red]{stats.orphaned_debug}[/]",
                classes="warning" if stats.orphaned_debug else "",
            )
        )
        row_orphaned.mount(
            StatCard(
                f"Orphaned Todos\n\n[bold red]{stats.orphaned_todos}[/]",
                classes="warning" if stats.orphaned_todos else "",
            )
        )

        row_size = self.query_one("#row-size")
        row_size.remove_children()
        row_size.mount(StatCard(f".claude Dir Size\n\n[bold]{_format_bytes(stats.claude_dir_size)}[/]"))
        row_size.mount(StatCard(f"Projects Dir Size\n\n[bold]{_format_bytes(stats.projects_dir_size)}[/]"))
