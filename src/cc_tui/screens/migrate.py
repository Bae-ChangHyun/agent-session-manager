"""Session migration screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, RadioButton, RadioSet, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.migrate import get_available_projects, migrate_sessions


class MigratePane(Container):
    """Session migration between projects."""

    CSS = """
    MigratePane {
        height: 1fr;
        padding: 1;
    }
    #migrate-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #migrate-form {
        height: auto;
        margin-bottom: 1;
    }
    .form-row {
        height: auto;
        margin-bottom: 1;
    }
    .form-label {
        width: 15;
        height: 3;
        content-align: left middle;
    }
    .form-input {
        width: 1fr;
    }
    #migrate-projects-table {
        height: 1fr;
    }
    #migrate-result {
        height: auto;
        margin-top: 1;
        padding: 1;
        border: round $success;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Migrate sessions from one project to another. "
            "Copy-based (source is preserved). Select a project below or type a path.",
            id="migrate-info",
        )
        with Vertical(id="migrate-form"):
            with Horizontal(classes="form-row"):
                yield Label("Source Path:", classes="form-label")
                yield Input(placeholder="Source project path (absolute)", id="migrate-source", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Target Path:", classes="form-label")
                yield Input(placeholder="Target project path (absolute)", id="migrate-target", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Mode:", classes="form-label")
                with RadioSet(id="migrate-mode"):
                    yield RadioButton("Append (keep existing, skip duplicates)", value=True)
                    yield RadioButton("Overwrite (delete existing first)")
            yield Button("Migrate", variant="primary", id="btn-migrate")
        yield Static("", id="migrate-result")
        yield Static("Available Projects (click to set as source):", classes="section-title")
        yield DataTable(id="migrate-projects-table")

    def on_mount(self) -> None:
        table = self.query_one("#migrate-projects-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Encoded Name", "Path Hint")
        self.run_worker(self._load_projects, thread=True)

    def _load_projects(self) -> None:
        projects = get_available_projects()
        self.app.call_from_thread(self._update_table, projects)

    def _update_table(self, projects) -> None:
        table = self.query_one("#migrate-projects-table", DataTable)
        table.clear()
        for encoded, hint in projects:
            table.add_row(encoded, hint, key=encoded)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Set source path when a project row is selected."""
        if event.data_table.id == "migrate-projects-table":
            # Get the hint path from the selected row
            row_data = event.data_table.get_row(event.row_key)
            hint = str(row_data[1])
            source_input = self.query_one("#migrate-source", Input)
            source_input.value = hint

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-migrate":
            source = self.query_one("#migrate-source", Input).value.strip()
            target = self.query_one("#migrate-target", Input).value.strip()
            if not source or not target:
                self.app.notify("Source and target paths are required", severity="error")
                return

            radio_set = self.query_one("#migrate-mode", RadioSet)
            mode = "append" if radio_set.pressed_index == 0 else "overwrite"

            self.app.push_screen(
                ConfirmScreen(
                    f"Migrate sessions?\n\n"
                    f"Source: {source}\n"
                    f"Target: {target}\n"
                    f"Mode: {mode}"
                ),
                callback=lambda ok: self._do_migrate(source, target, mode) if ok else None,
            )

    def _do_migrate(self, source: str, target: str, mode: str) -> None:
        self.run_worker(lambda: self._execute_migrate(source, target, mode), thread=True)

    def _execute_migrate(self, source: str, target: str, mode: str) -> None:
        result = migrate_sessions(source, target, mode)
        self.app.call_from_thread(self._show_result, result)

    def _show_result(self, result) -> None:
        result_widget = self.query_one("#migrate-result", Static)
        if result.success:
            result_widget.update(
                f"[green]Migration complete![/]\n"
                f"Sessions copied: {result.sessions_copied}\n"
                f"Memory copied: {'Yes' if result.memory_copied else 'No'}\n"
                f"{result.message}"
            )
            self.app.notify("Migration complete!")
        else:
            result_widget.update(f"[red]Migration failed:[/] {result.message}")
            self.app.notify("Migration failed", severity="error")
        result_widget.display = True
