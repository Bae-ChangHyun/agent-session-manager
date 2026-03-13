"""File history management screen."""

import re

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from cc_tui.models import decode_path_hint, encode_path
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_file_history, get_project_paths, _get_session_to_project_map
from cc_tui.i18n import t
from cc_tui.services.cleaner import trash_file_history, trash_file_histories

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _display_name(dir_name: str, encoded_to_path: dict) -> str:
    """Convert dir_name to a readable display name."""
    actual = encoded_to_path.get(dir_name)
    if actual:
        return actual
    if _UUID_RE.match(dir_name):
        return f"[dim]Session:[/] {dir_name[:8]}..."
    return decode_path_hint(dir_name)


class FileHistoryPane(Container):
    """View and manage file history entries."""

    CSS = """
    FileHistoryPane {
        height: 1fr;
        padding: 1;
    }
    #fh-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #fh-layout {
        height: 1fr;
    }
    #fh-list-panel {
        width: 1fr;
        height: 1fr;
    }
    #fh-actions {
        height: 1;
        margin-top: 1;
    }
    #fh-detail-panel {
        width: 1fr;
        height: 1fr;
        max-width: 50%;
        border-left: tall $primary;
        padding: 0 1;
    }
    #fh-detail {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            t("fh.info"),
            id="fh-info",
        )
        with Horizontal(id="fh-layout"):
            with Vertical(id="fh-list-panel"):
                yield DataTable(id="fh-table")
                yield Static("", id="fh-actions")
            with Vertical(id="fh-detail-panel"):
                yield VerticalScroll(
                    Static(t("fh.select_hint"), id="fh-detail-body"),
                    id="fh-detail",
                )

    def on_mount(self) -> None:
        table = self.query_one("#fh-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.styles.height = "1fr"
        table.add_columns("Project / Session", "Status")
        self._orphaned_fh_names = []
        self._action_map = []
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        entries = get_file_history()
        project_paths = get_project_paths()
        encoded_to_path = {encode_path(p): p for p in project_paths}
        session_to_project = _get_session_to_project_map()
        self.app.call_from_thread(self._update_table, entries, encoded_to_path, session_to_project)

    def _update_table(self, entries, encoded_to_path: dict, session_to_project: dict = None) -> None:
        table = self.query_one("#fh-table", DataTable)
        table.clear()
        self._entries = {e.dir_name: e for e in entries}
        self._encoded_to_path = encoded_to_path
        self._session_to_project = session_to_project or {}
        self._orphaned_fh_names = [e.dir_name for e in entries if e.is_orphaned]
        # Group by project
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        orphaned = []
        for e in entries:
            if e.is_orphaned:
                orphaned.append(e)
            else:
                project = self._session_to_project.get(e.dir_name)
                display = project if project else _display_name(e.dir_name, encoded_to_path)
                groups[display].append(e)

        if orphaned:
            table.add_row(
                f"[bold yellow]── Orphaned ({len(orphaned)})[/]", "",
                key="__hdr_orphaned__",
            )
            for i, e in enumerate(orphaned, 1):
                table.add_row(f"  [yellow]Orphan {i}[/]", t("common.orphaned"), key=e.dir_name)

        for project in sorted(groups.keys()):
            items = groups[project]
            table.add_row(
                f"[bold cyan]── {project} ({len(items)})[/]", "",
                key=f"__hdr_{project}__",
            )
            for i, e in enumerate(items, 1):
                table.add_row(f"  Session {i}", t("common.active"), key=e.dir_name)
        self._render_actions()

    def _render_actions(self) -> None:
        """Render action bar with click-mapped Rich markup buttons."""
        actions = [("trash-selected", t("fh.btn_trash"), "#e8890c")]
        count = len(getattr(self, "_orphaned_fh_names", []))
        if count > 0:
            actions.append(("trash-orphaned", t("fh.btn_trash_orphaned", count=count), "#ba3c5b"))
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
        self.query_one("#fh-actions", Static).update("  ".join(parts))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not event.row_key or event.row_key.value.startswith("__hdr_"):
            return
        if event.row_key.value in self._entries:
            e = self._entries[event.row_key.value]
            body = self.query_one("#fh-detail-body", Static)

            is_uuid = bool(_UUID_RE.match(e.dir_name))
            project = self._session_to_project.get(e.dir_name)

            if e.is_orphaned:
                status_msg = (
                    "[yellow bold]Orphaned[/]\n"
                    "[dim]세션이 삭제되어 매칭되지 않습니다.\n"
                    "안전하게 삭제 가능합니다.[/]"
                )
            else:
                status_msg = (
                    "[green bold]Active[/]\n"
                    "[dim]현재 프로젝트와 연결되어 있습니다.\n"
                    "삭제 시 해당 프로젝트의 파일 되돌리기 기능을 사용할 수 없습니다.[/]"
                )

            detail = f"[bold]Session ID:[/]\n  [dim]{e.dir_name}[/]\n\n"
            if project:
                detail += f"[bold]Project:[/]\n  {project}\n\n"
            detail += f"[bold]Status:[/] {status_msg}"
            body.update(detail)

    def on_click(self, event) -> None:
        """Handle action bar clicks."""
        if getattr(event.widget, "id", "") != "fh-actions":
            return
        for start, end, action_id in self._action_map:
            if start <= event.x < end:
                if action_id == "trash-selected":
                    self._click_trash_selected()
                elif action_id == "trash-orphaned":
                    self._click_trash_orphaned()
                break

    def _click_trash_selected(self) -> None:
        table = self.query_one("#fh-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key = list(table.rows.keys())[table.cursor_row]
            name = row_key.value
            if name.startswith("__hdr_"):
                return
            display = _display_name(name, self._encoded_to_path)
            self.app.push_screen(
                ConfirmScreen(
                    t("fh.confirm_trash", name=display)
                ),
                callback=lambda ok, n=name: self._do_trash(n) if ok else None,
            )

    def _click_trash_orphaned(self) -> None:
        names = getattr(self, "_orphaned_fh_names", [])
        if not names:
            self.app.notify(t("common.no_items"))
            return
        self.app.push_screen(
            ConfirmScreen(t("fh.confirm_trash_orphaned", count=len(names))),
            callback=lambda ok: self._do_trash_orphaned() if ok else None,
        )

    def _do_trash(self, name: str) -> None:
        if trash_file_history(name):
            self.app.notify(t("common.trashed", name=name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _do_trash_orphaned(self) -> None:
        names = getattr(self, "_orphaned_fh_names", [])
        ok, fail = trash_file_histories(names)
        self.app.notify(t("common.trash_bulk_ok", ok=ok, fail=fail))
        self.refresh_data()
