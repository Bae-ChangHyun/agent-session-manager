"""Debug files and Todos management screen."""

from pathlib import Path

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from cc_tui.models import DEBUG_DIR, TODOS_DIR
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_debug_files, get_todos, _get_session_to_project_map
from cc_tui.i18n import t
from cc_tui.services.cleaner import (
    count_empty_files,
    prune_empty_debug_files,
    prune_empty_todo_files,
    trash_debug_file,
    trash_debug_files,
    trash_todo_file,
    trash_todo_files,
)


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class DebugTodosPane(Container):
    """View and manage debug files and todos."""

    BINDINGS = [
        ("space", "toggle_select", "Select"),
    ]

    CSS = """
    DebugTodosPane {
        height: 1fr;
        padding: 1;
    }
    #dt-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #dt-layout {
        height: 1fr;
    }
    #dt-tables-panel {
        width: 1fr;
        height: 1fr;
    }
    .dt-section {
        height: 1fr;
        margin-bottom: 1;
    }
    .section-title {
        text-style: bold;
        margin-bottom: 0;
    }
    .dt-action-bar {
        height: 1;
        margin-top: 1;
    }
    #dt-preview-panel {
        width: 1fr;
        height: 1fr;
        max-width: 50%;
        border-left: tall $primary;
        padding: 0 1;
    }
    #dt-preview-scroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            t("dt.info"),
            id="dt-info",
        )
        with Horizontal(id="dt-layout"):
            with Vertical(id="dt-tables-panel"):
                with Vertical(classes="dt-section"):
                    yield Static("", classes="section-title", id="debug-title")
                    yield DataTable(id="debug-table")
                    yield Static("", id="debug-actions", classes="dt-action-bar")
                with Vertical(classes="dt-section"):
                    yield Static("", classes="section-title", id="todo-title")
                    yield DataTable(id="todo-table")
                    yield Static("", id="todo-actions", classes="dt-action-bar")
            with Vertical(id="dt-preview-panel"):
                yield Static("[bold]Content Preview[/]", id="dt-preview-header")
                yield VerticalScroll(
                    Static(f"[dim]{t('dt.select_file')}[/]", id="dt-preview-body"),
                    id="dt-preview-scroll",
                )

    def on_mount(self) -> None:
        dt = self.query_one("#debug-table", DataTable)
        dt.cursor_type = "row"
        dt.zebra_stripes = True
        dt.styles.height = "1fr"
        dt.add_columns("Name", "Size", "Status")

        tt = self.query_one("#todo-table", DataTable)
        tt.cursor_type = "row"
        tt.zebra_stripes = True
        tt.styles.height = "1fr"
        tt.add_columns("Name", "Size", "Status")

        self._debug_action_map = []
        self._todo_action_map = []
        self._orphaned_debug_names = []
        self._orphaned_todo_names = []
        self._empty_debug = 0
        self._empty_todo = 0
        self._selected_debug: set[str] = set()
        self._selected_todo: set[str] = set()
        self._debug_row_display: dict[str, str] = {}
        self._todo_row_display: dict[str, str] = {}
        self._debug_group_items: dict[str, list[str]] = {}
        self._todo_group_items: dict[str, list[str]] = {}
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        debug = get_debug_files()
        todos = get_todos()
        empty_debug = count_empty_files(DEBUG_DIR)
        empty_todo = count_empty_files(TODOS_DIR)
        session_to_project = _get_session_to_project_map()
        self.app.call_from_thread(self._update, debug, todos, empty_debug, empty_todo, session_to_project)

    def _update(self, debug, todos, empty_debug: int = 0, empty_todo: int = 0, session_to_project: dict = None) -> None:
        self._debug_entries = {d.name: d for d in debug}
        self._todo_entries = {td.name: td for td in todos}
        self._session_to_project = session_to_project or {}

        orphaned_debug = sum(1 for d in debug if d.is_orphaned)
        orphaned_todos = sum(1 for td in todos if td.is_orphaned)
        self._orphaned_debug_names = [d.name for d in debug if d.is_orphaned]
        self._orphaned_todo_names = [td.name for td in todos if td.is_orphaned]
        self._empty_debug = empty_debug
        self._empty_todo = empty_todo

        self.query_one("#debug-title", Static).update(
            f"[bold]Debug Files[/]  [dim]({len(debug)}개, orphaned: [yellow]{orphaned_debug}[/])[/]"
        )
        self.query_one("#todo-title", Static).update(
            f"[bold]Todo Files[/]  [dim]({len(todos)}개, orphaned: [yellow]{orphaned_todos}[/])[/]"
        )

        self._selected_debug.clear()
        self._selected_todo.clear()

        dt = self.query_one("#debug-table", DataTable)
        dt.clear()
        if debug:
            gi, rd = self._populate_grouped_table(
                dt, debug,
                key_fn=lambda d: d.name.split(".")[0],
            )
            self._debug_group_items = gi
            self._debug_row_display = rd
        else:
            dt.add_row(f"[dim]{t('dt.none')}[/]", "", "")
            self._debug_group_items = {}
            self._debug_row_display = {}

        tt = self.query_one("#todo-table", DataTable)
        tt.clear()
        if todos:
            gi, rd = self._populate_grouped_table(
                tt, todos,
                key_fn=lambda td: td.name.split("-agent-")[0] if "-agent-" in td.name else td.name.split(".")[0],
            )
            self._todo_group_items = gi
            self._todo_row_display = rd
        else:
            tt.add_row(f"[dim]{t('dt.none')}[/]", "", "")
            self._todo_group_items = {}
            self._todo_row_display = {}

        self._render_debug_actions()
        self._render_todo_actions()

    def _populate_grouped_table(self, table: DataTable, entries, key_fn):
        """Populate a DataTable with entries grouped by project.

        Returns (group_items, row_display) for group delete and multi-select.
        """
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        orphaned = []
        group_items: dict[str, list[str]] = {}
        row_display: dict[str, str] = {}

        for e in entries:
            if e.is_orphaned:
                orphaned.append(e)
            else:
                session_id = key_fn(e)
                project = self._session_to_project.get(session_id, session_id)
                groups[project].append(e)

        # Orphaned group first
        if orphaned:
            hdr = "__hdr_orphaned__"
            table.add_row(
                f"[bold yellow]── Orphaned ({len(orphaned)})[/]", "", "",
                key=hdr,
            )
            group_items[hdr] = [e.name for e in orphaned]
            for i, e in enumerate(orphaned, 1):
                display = f"[yellow]Orphan {i}[/]"
                row_display[e.name] = display
                table.add_row(
                    f"  {display}",
                    _format_bytes(e.size_bytes),
                    t("common.orphaned"),
                    key=e.name,
                )

        # Active groups by project
        for project in sorted(groups.keys()):
            items = groups[project]
            total_size = sum(e.size_bytes for e in items)
            hdr = f"__hdr_{project}__"
            table.add_row(
                f"[bold cyan]── {project} ({len(items)})[/]",
                f"[dim]{_format_bytes(total_size)}[/]", "",
                key=hdr,
            )
            group_items[hdr] = [e.name for e in items]
            for i, e in enumerate(items, 1):
                display = f"Session {i}"
                row_display[e.name] = display
                table.add_row(
                    f"  {display}",
                    _format_bytes(e.size_bytes),
                    t("common.active"),
                    key=e.name,
                )

        return group_items, row_display

    def _build_action_bar(self, actions):
        """Build Rich markup action bar and click map.

        actions: list of (action_id, label, color)
        """
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
        return "  ".join(parts), click_map

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row (spacebar)."""
        focused = self.app.focused
        if focused is None:
            return
        table_id = getattr(focused, "id", "")
        if table_id == "debug-table":
            selected = self._selected_debug
            row_display = self._debug_row_display
        elif table_id == "todo-table":
            selected = self._selected_todo
            row_display = self._todo_row_display
        else:
            return
        table = focused
        if table.cursor_row is None or table.row_count == 0:
            return
        row_key = list(table.rows.keys())[table.cursor_row]
        name = row_key.value
        if name.startswith("__hdr_") or name not in row_display:
            return
        name_col = list(table.columns.keys())[0]
        if name in selected:
            selected.discard(name)
            table.update_cell(row_key, name_col, f"  {row_display[name]}")
        else:
            selected.add(name)
            table.update_cell(row_key, name_col, f"  [bold green]●[/] {row_display[name]}")
        self._render_debug_actions()
        self._render_todo_actions()

    def _render_debug_actions(self) -> None:
        sel = len(self._selected_debug)
        trash_label = t("dt.btn_trash_debug") + (f" ({sel})" if sel else "")
        actions = [("trash-debug", trash_label, "#e8890c")]
        if self._empty_debug > 0:
            actions.append(("prune-debug", t("dt.btn_prune_debug", count=self._empty_debug), "#0178d4"))
        if len(self._orphaned_debug_names) > 0:
            actions.append(("trash-orphaned-debug", t("dt.btn_trash_orphaned_debug", count=len(self._orphaned_debug_names)), "#ba3c5b"))
        markup, click_map = self._build_action_bar(actions)
        self._debug_action_map = click_map
        self.query_one("#debug-actions", Static).update(markup)

    def _render_todo_actions(self) -> None:
        sel = len(self._selected_todo)
        trash_label = t("dt.btn_trash_todo") + (f" ({sel})" if sel else "")
        actions = [("trash-todo", trash_label, "#e8890c")]
        if self._empty_todo > 0:
            actions.append(("prune-todo", t("dt.btn_prune_todo", count=self._empty_todo), "#0178d4"))
        if len(self._orphaned_todo_names) > 0:
            actions.append(("trash-orphaned-todo", t("dt.btn_trash_orphaned_todo", count=len(self._orphaned_todo_names)), "#ba3c5b"))
        markup, click_map = self._build_action_bar(actions)
        self._todo_action_map = click_map
        self.query_one("#todo-actions", Static).update(markup)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show file content preview when a row is highlighted."""
        if not event.row_key:
            return
        name = event.row_key.value
        entry = self._debug_entries.get(name) or self._todo_entries.get(name)
        if not entry:
            return
        self.run_worker(lambda: self._read_preview(entry.path, entry.name), thread=True)

    def _read_preview(self, file_path: str, name: str) -> None:
        """Read file content for preview."""
        try:
            p = Path(file_path)
            if p.is_file():
                content = p.read_text(errors="replace")[:2000]
            elif p.is_dir():
                files = list(p.iterdir())[:20]
                content = f"Directory with {len(list(p.iterdir()))} items:\n\n"
                for f in files:
                    size = f.stat().st_size if f.is_file() else 0
                    content += f"  {f.name}  ({_format_bytes(size)})\n"
            else:
                content = "(not found)"
        except OSError as e:
            content = f"(read error: {e})"
        self.app.call_from_thread(self._show_preview, name, content)

    def _show_preview(self, name: str, content: str) -> None:
        from rich.text import Text
        body = self.query_one("#dt-preview-body", Static)
        text = Text()
        text.append(name, style="bold")
        text.append("\n" + "─" * 40 + "\n")
        stripped = content.strip()
        if stripped in ("[]", "{}", ""):
            empty_text = t("dt.empty_file")
            lines = empty_text.split("\n")
            text.append(lines[0] + "\n", style="dim")
            if len(lines) > 1:
                text.append(lines[1], style="dim italic")
        else:
            text.append(content)
        body.update(text)

    def on_click(self, event) -> None:
        """Handle action bar clicks."""
        widget_id = getattr(event.widget, "id", "")
        if widget_id == "debug-actions":
            action_map = self._debug_action_map
        elif widget_id == "todo-actions":
            action_map = self._todo_action_map
        else:
            return
        for start, end, action_id in action_map:
            if start <= event.x < end:
                self._handle_action(action_id)
                break

    def _handle_action(self, action_id: str) -> None:
        if action_id == "trash-debug":
            # Multi-select mode
            if self._selected_debug:
                names = list(self._selected_debug)
                self.app.push_screen(
                    ConfirmScreen(f"선택한 {len(names)}개 debug 파일을 삭제하시겠습니까?"),
                    callback=lambda ok, ns=names: self._do_trash_bulk("debug", ns) if ok else None,
                )
                return
            table = self.query_one("#debug-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                name = row_key.value
                # Group delete
                if name.startswith("__hdr_"):
                    items = self._debug_group_items.get(name, [])
                    if items:
                        self.app.push_screen(
                            ConfirmScreen(f"이 그룹의 {len(items)}개 debug 파일을 삭제하시겠습니까?"),
                            callback=lambda ok, ns=items: self._do_trash_bulk("debug", ns) if ok else None,
                        )
                    return
                self.app.push_screen(
                    ConfirmScreen(t("dt.confirm_debug", name=name)),
                    callback=lambda ok, n=name: self._trash_debug(n) if ok else None,
                )
        elif action_id == "trash-todo":
            # Multi-select mode
            if self._selected_todo:
                names = list(self._selected_todo)
                self.app.push_screen(
                    ConfirmScreen(f"선택한 {len(names)}개 todo 파일을 삭제하시겠습니까?"),
                    callback=lambda ok, ns=names: self._do_trash_bulk("todo", ns) if ok else None,
                )
                return
            table = self.query_one("#todo-table", DataTable)
            if table.cursor_row is not None and table.row_count > 0:
                row_key = list(table.rows.keys())[table.cursor_row]
                name = row_key.value
                # Group delete
                if name.startswith("__hdr_"):
                    items = self._todo_group_items.get(name, [])
                    if items:
                        self.app.push_screen(
                            ConfirmScreen(f"이 그룹의 {len(items)}개 todo 파일을 삭제하시겠습니까?"),
                            callback=lambda ok, ns=items: self._do_trash_bulk("todo", ns) if ok else None,
                        )
                    return
                self.app.push_screen(
                    ConfirmScreen(t("dt.confirm_todo", name=name)),
                    callback=lambda ok, n=name: self._trash_todo(n) if ok else None,
                )
        elif action_id == "prune-debug":
            count = count_empty_files(DEBUG_DIR)
            if count == 0:
                self.app.notify(t("common.no_items"))
                return
            self.app.push_screen(
                ConfirmScreen(t("dt.confirm_prune_debug", count=count)),
                callback=lambda ok: self._do_prune_debug() if ok else None,
            )
        elif action_id == "prune-todo":
            count = count_empty_files(TODOS_DIR)
            if count == 0:
                self.app.notify(t("common.no_items"))
                return
            self.app.push_screen(
                ConfirmScreen(t("dt.confirm_prune_todo", count=count)),
                callback=lambda ok: self._do_prune_todo() if ok else None,
            )
        elif action_id == "trash-orphaned-debug":
            names = getattr(self, "_orphaned_debug_names", [])
            if not names:
                self.app.notify(t("common.no_items"))
                return
            self.app.push_screen(
                ConfirmScreen(t("dt.confirm_trash_orphaned_debug", count=len(names))),
                callback=lambda ok: self._do_trash_orphaned_debug() if ok else None,
            )
        elif action_id == "trash-orphaned-todo":
            names = getattr(self, "_orphaned_todo_names", [])
            if not names:
                self.app.notify(t("common.no_items"))
                return
            self.app.push_screen(
                ConfirmScreen(t("dt.confirm_trash_orphaned_todo", count=len(names))),
                callback=lambda ok: self._do_trash_orphaned_todo() if ok else None,
            )

    def _trash_debug(self, name: str) -> None:
        if trash_debug_file(name):
            self.app.notify(t("common.trashed", name=name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _trash_todo(self, name: str) -> None:
        if trash_todo_file(name):
            self.app.notify(t("common.trashed", name=name))
            self.refresh_data()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def _do_prune_debug(self) -> None:
        ok, fail = prune_empty_debug_files()
        self.app.notify(t("dt.prune_ok", ok=ok))
        self.refresh_data()

    def _do_prune_todo(self) -> None:
        ok, fail = prune_empty_todo_files()
        self.app.notify(t("dt.prune_ok", ok=ok))
        self.refresh_data()

    def _do_trash_bulk(self, kind: str, names: list[str]) -> None:
        """Bulk delete for multi-select and group delete."""
        if kind == "debug":
            ok, fail = trash_debug_files(names)
            self._selected_debug.clear()
        else:
            ok, fail = trash_todo_files(names)
            self._selected_todo.clear()
        self.app.notify(t("common.trash_bulk_ok", ok=ok, fail=fail))
        self.refresh_data()

    def _do_trash_orphaned_debug(self) -> None:
        names = getattr(self, "_orphaned_debug_names", [])
        ok, fail = trash_debug_files(names)
        self.app.notify(t("common.trash_bulk_ok", ok=ok, fail=fail))
        self.refresh_data()

    def _do_trash_orphaned_todo(self) -> None:
        names = getattr(self, "_orphaned_todo_names", [])
        ok, fail = trash_todo_files(names)
        self.app.notify(t("common.trash_bulk_ok", ok=ok, fail=fail))
        self.refresh_data()
