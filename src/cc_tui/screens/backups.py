"""Backups management screen."""

from datetime import datetime

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
from cc_tui.utils import format_bytes
from cc_tui.widgets.action_bar import ActionBar


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
        yield ActionBar(id="backup-actions")
        yield DataTable(id="backups-table")

    def on_mount(self) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Name", "Created", "Size", "Path")
        self._render_actions()
        self.refresh_data()

    def _render_actions(self) -> None:
        actions = [
            ("config-backup", t("bak.btn_config"), "#0178d4"),
            ("full-backup", t("bak.btn_full"), "#0178d4"),
            ("restore", t("bak.btn_restore"), "#4EBF71"),
            ("delete", t("bak.btn_delete"), "#ba3c5b"),
        ]
        bar = self.query_one("#backup-actions", ActionBar)
        bar.set_actions(actions, on_action=self._handle_action)

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
            table.add_row(b.name, created, format_bytes(b.size_bytes), b.path, key=b.name)

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
            self.app.call_from_thread(self.app.notify, t("bak.config_created", path=path))
        else:
            self.app.call_from_thread(self.app.notify, t("bak.backup_failed"), severity="error")
        self.app.call_from_thread(self.refresh_data)

    def _do_full_backup(self) -> None:
        self.app.call_from_thread(self.app.notify, t("bak.full_creating"))
        path = create_full_backup()
        if path:
            self.app.call_from_thread(self.app.notify, t("bak.full_created", path=path))
        else:
            self.app.call_from_thread(self.app.notify, t("bak.backup_failed"), severity="error")
        self.app.call_from_thread(self.refresh_data)

    def _do_restore(self, backup, is_full: bool) -> None:
        def _work():
            if is_full:
                ok = restore_full_backup(backup.path)
            else:
                ok = restore_config_backup(backup.path)
            if ok:
                self.app.call_from_thread(self.app.notify, t("bak.restored", name=backup.name))
            else:
                self.app.call_from_thread(self.app.notify, t("bak.restore_failed"), severity="error")
            self.app.call_from_thread(self.refresh_data)
        self.run_worker(_work, thread=True)

    def _do_delete(self, backup) -> None:
        def _work():
            if delete_backup(backup.path):
                self.app.call_from_thread(self.app.notify, t("bak.deleted", name=backup.name))
            else:
                self.app.call_from_thread(self.app.notify, t("bak.delete_failed"), severity="error")
            self.app.call_from_thread(self.refresh_data)
        self.run_worker(_work, thread=True)
