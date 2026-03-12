"""Projects management screen."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.backup import create_config_backup
from cc_tui.services.claude_data import get_projects, remove_project_from_json


class ProjectsPane(Container):
    """View and manage projects from .claude.json."""

    CSS = """
    ProjectsPane {
        height: 1fr;
        padding: 1;
    }
    #projects-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #projects-actions {
        height: 3;
        margin-bottom: 1;
    }
    #projects-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Projects registered in .claude.json. Remove entries for projects no longer needed.",
            id="projects-info",
        )
        yield Button("Remove Selected from Config", variant="error", id="btn-remove-projects")
        yield DataTable(id="projects-table")

    def on_mount(self) -> None:
        table = self.query_one("#projects-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Path", "Status", "Last Cost", "Duration", "Session Envs")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_projects, thread=True)

    def _load_projects(self) -> None:
        projects = get_projects()
        self.app.call_from_thread(self._update_table, projects)

    def _update_table(self, projects) -> None:
        table = self.query_one("#projects-table", DataTable)
        table.clear()
        self._projects = projects
        for p in projects:
            status = "[green]Found[/]" if p.exists else "[red]Missing[/]"
            cost = f"${p.last_cost:.4f}" if p.last_cost else "N/A"
            duration = f"{p.last_duration:.0f}s" if p.last_duration else "N/A"
            envs = str(len(p.session_env_dirs))
            table.add_row(p.path, status, cost, duration, envs, key=p.path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-remove-projects":
            table = self.query_one("#projects-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = table.get_row_at(table.cursor_row)
                path = str(list(table.rows.keys())[table.cursor_row].value)
                self.app.push_screen(
                    ConfirmScreen(f"Remove '{path}' from config?"),
                    callback=lambda ok: self._do_remove(path) if ok else None,
                )

    def _do_remove(self, path: str) -> None:
        create_config_backup()
        if remove_project_from_json(path):
            self.app.notify(f"Removed: {path}")
            self.refresh_data()
        else:
            self.app.notify("Failed to remove", severity="error")
