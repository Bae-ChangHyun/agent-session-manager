"""Backups management screen."""

from datetime import datetime

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from cc_tui.i18n import t
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

    BINDINGS = [
        ("c", "config_backup", "Config Backup"),
        ("b", "full_backup", "Full Backup"),
        ("R", "restore_backup", "Restore"),
        ("d", "delete_backup", "Delete"),
    ]

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
        height: 1;
        margin-bottom: 1;
    }
    #backups-table {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            t("bak.info"),
            id="backups-info",
        )
        yield Static("", id="backup-actions")
        yield DataTable(id="backups-table")

    def on_mount(self) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Name", "Created", "Size", "Path")
        self._action_map = []
        self._render_actions()
        self.refresh_data()

    def _render_actions(self) -> None:
        actions = [
            ("config-backup", t("bak.btn_config"), "#0178d4"),
            ("full-backup", t("bak.btn_full"), "#0178d4"),
            ("restore", t("bak.btn_restore"), "#4EBF71"),
            ("delete", t("bak.btn_delete"), "#ba3c5b"),
        ]
        parts = []
        click_map = []
        x = 0
        for i, (action_id, label, color) in enumerate(actions):
            text = f" {label} "
            width = cell_len(text)
            click_map.append((x, x + width, action_id))
            parts.append(f"[bold white on {color}]{text}[/]")
            x += width
            if i < len(actions) - 1:
                x += 2
        self._action_map = click_map
        self.query_one("#backup-actions", Static).update("  ".join(parts))

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

    def action_config_backup(self) -> None:
        self._handle_action("config-backup")

    def action_full_backup(self) -> None:
        self._handle_action("full-backup")

    def action_restore_backup(self) -> None:
        self._handle_action("restore")

    def action_delete_backup(self) -> None:
        self._handle_action("delete")

    def on_click(self, event) -> None:
        """Handle action bar clicks."""
        if getattr(event.widget, "id", "") != "backup-actions":
            return
        for start, end, action_id in self._action_map:
            if start <= event.x < end:
                self._handle_action(action_id)
                break

    def _handle_action(self, action_id: str) -> None:
        if action_id == "config-backup":
            self.run_worker(self._do_config_backup, thread=True)
        elif action_id == "full-backup":
            self.app.push_screen(
                ConfirmScreen(t("bak.confirm_full")),
                callback=lambda ok: self.run_worker(self._do_full_backup, thread=True) if ok else None,
            )
        elif action_id == "restore":
            backup = self._get_selected_backup()
            if backup:
                is_full = "[full]" in backup.name
                self.app.push_screen(
                    ConfirmScreen(t("bak.confirm_restore", name=backup.name)),
                    callback=lambda ok, b=backup, f=is_full: self._do_restore(b, f) if ok else None,
                )
        elif action_id == "delete":
            backup = self._get_selected_backup()
            if backup:
                self.app.push_screen(
                    ConfirmScreen(t("bak.confirm_delete", name=backup.name)),
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
