"""Backups management screen."""

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Static

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.backup import (
    create_config_backup,
    create_full_backup,
    delete_backup,
    list_backups,
    restore_config_backup,
    restore_full_backup,
)


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class BackupsPane(Container):
    """View, create, restore, and manage backups."""

    CSS = """
    BackupsPane {
        height: 1fr;
        padding: 1;
    }
    #backups-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #backup-actions {
        height: auto;
        margin-bottom: 1;
    }
    #backup-actions Button {
        margin-right: 1;
    }
    #backups-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Backups[/] - 설정/전체 백업 생성 및 복원\n"
            "[dim]~/.cc-tui/backups/ 에 저장됩니다. 작업 전 백업을 만들어두면 실수해도 복구할 수 있습니다.[/]",
            id="backups-info",
        )
        with Horizontal(id="backup-actions"):
            yield Button("Create Config Backup", variant="primary", id="btn-config-backup")
            yield Button("Create Full Backup", variant="warning", id="btn-full-backup")
            yield Button("Restore Selected", variant="success", id="btn-restore")
            yield Button("Delete Selected", variant="error", id="btn-delete-backup")
        yield DataTable(id="backups-table")

    def on_mount(self) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Name", "Created", "Size", "Path")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        backups = list_backups()
        self.app.call_from_thread(self._update, backups)

    def _update(self, backups) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.clear()
        self._backups = {b.name: b for b in backups}
        for b in backups:
            created = datetime.fromtimestamp(b.created).strftime("%Y-%m-%d %H:%M:%S") if b.created else "N/A"
            table.add_row(b.name, created, _format_bytes(b.size_bytes), b.path, key=b.name)

    def _get_selected_backup(self):
        table = self.query_one("#backups-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key = list(table.rows.keys())[table.cursor_row]
            return self._backups.get(row_key.value)
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-config-backup":
            self.run_worker(self._do_config_backup, thread=True)
        elif event.button.id == "btn-full-backup":
            self.app.push_screen(
                ConfirmScreen("Create a full backup of .claude directory?\nThis may take a moment."),
                callback=lambda ok: self.run_worker(self._do_full_backup, thread=True) if ok else None,
            )
        elif event.button.id == "btn-restore":
            backup = self._get_selected_backup()
            if backup:
                is_full = "[full]" in backup.name
                self.app.push_screen(
                    ConfirmScreen(f"Restore backup '{backup.name}'?\nCurrent config will be backed up first."),
                    callback=lambda ok, b=backup, f=is_full: self._do_restore(b, f) if ok else None,
                )
        elif event.button.id == "btn-delete-backup":
            backup = self._get_selected_backup()
            if backup:
                self.app.push_screen(
                    ConfirmScreen(f"Delete backup '{backup.name}'?"),
                    callback=lambda ok, b=backup: self._do_delete(b) if ok else None,
                )

    def _do_config_backup(self) -> None:
        path = create_config_backup()
        if path:
            self.app.call_from_thread(self.app.notify, f"Config backup created: {path}")
        else:
            self.app.call_from_thread(self.app.notify, "Failed to create backup", severity="error")
        self.app.call_from_thread(self.refresh_data)

    def _do_full_backup(self) -> None:
        self.app.call_from_thread(self.app.notify, "Creating full backup...")
        path = create_full_backup()
        if path:
            self.app.call_from_thread(self.app.notify, f"Full backup created: {path}")
        else:
            self.app.call_from_thread(self.app.notify, "Failed to create backup", severity="error")
        self.app.call_from_thread(self.refresh_data)

    def _do_restore(self, backup, is_full: bool) -> None:
        if is_full:
            ok = restore_full_backup(backup.path)
        else:
            ok = restore_config_backup(backup.path)
        if ok:
            self.app.notify(f"Restored: {backup.name}")
        else:
            self.app.notify("Restore failed", severity="error")
        self.refresh_data()

    def _do_delete(self, backup) -> None:
        if delete_backup(backup.path):
            self.app.notify(f"Deleted: {backup.name}")
        else:
            self.app.notify("Delete failed", severity="error")
        self.refresh_data()
