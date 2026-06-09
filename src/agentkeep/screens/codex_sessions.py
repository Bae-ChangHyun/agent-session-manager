"""Codex sessions screen — browse rollout sessions grouped by working dir."""

from __future__ import annotations

from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Static, Tree

from agentkeep.i18n import t
from agentkeep.services import codex_data
from agentkeep.screens.confirm import ConfirmScreen
from agentkeep.services.cleaner import trash_codex_session
from agentkeep.widgets.action_bar import ActionBar


class CodexSessionsPane(Container):
    """Browse, preview and trash Codex (~/.codex) sessions."""

    BINDINGS = [
        ("d", "trash_session", "Trash Session"),
    ]

    CSS = """
    CodexSessionsPane { height: 1fr; padding: 1; }
    #codex-info { height: auto; margin-bottom: 1; color: $text-muted; }
    #codex-layout { height: 1fr; }
    #codex-filter { margin-bottom: 1; }
    #codex-tree-panel { width: 1fr; height: 1fr; min-width: 40; }
    #codex-tree { height: 1fr; }
    #codex-actions { height: 1; margin-top: 1; }
    #codex-detail-panel { width: 1fr; height: 1fr; border-left: tall $primary; padding: 0 1; }
    #codex-detail-scroll { height: 1fr; }
    #codex-detail-header { height: auto; text-style: bold; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="codex-info")
        yield Input(placeholder=t("codex.filter_placeholder"), id="codex-filter")
        with Horizontal(id="codex-layout"):
            with Vertical(id="codex-tree-panel"):
                yield Tree("Codex", id="codex-tree")
                yield ActionBar(id="codex-actions")
            with Vertical(id="codex-detail-panel"):
                yield Static("", id="codex-detail-header")
                yield VerticalScroll(
                    Static(t("codex.select_hint"), id="codex-detail-body"),
                    id="codex-detail-scroll",
                )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._projects = []
        self._filter_query = ""
        self._selected = None  # (session_id, rollout_path)
        self._selected_node = None

    def on_mount(self) -> None:
        tree = self.query_one("#codex-tree", Tree)
        tree.show_root = False
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        if not codex_data.is_available():
            self.app.call_from_thread(self._show_unavailable)
            return
        projects = codex_data.get_projects()
        total = codex_data.total_session_count()
        self.app.call_from_thread(self._set_data, projects, total)

    def _show_unavailable(self) -> None:
        self.query_one("#codex-info", Static).update(t("codex.unavailable"))

    def _set_data(self, projects, total: int) -> None:
        self._projects = projects
        self.query_one("#codex-info", Static).update(
            t("codex.info", limit=min(codex_data.SCAN_LIMIT, total), total=total)
        )
        self._build_tree()
        self._render_actions()

    def _build_tree(self) -> None:
        tree = self.query_one("#codex-tree", Tree)
        tree.clear()
        query = self._filter_query.casefold()
        for p in self._projects:
            if query and query not in p.path.casefold():
                continue
            status = "[green]O[/]" if p.exists else "[red]X[/]"
            node = tree.root.add(f"{status} {p.path}", data=("project", p.path), expand=False)
            node.add_leaf("[dim]…[/]", data=("placeholder", None))

    def _render_actions(self) -> None:
        bar = self.query_one("#codex-actions", ActionBar)
        actions = []
        if self._selected:
            actions.append(("trash-session", t("codex.btn_trash_session"), "#e8890c"))
        bar.set_actions(actions, on_action=lambda aid: self.action_trash_session())

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        data = event.node.data
        if not data or data[0] != "project":
            return
        if any(c.data and c.data[0] == "placeholder" for c in event.node.children):
            self.run_worker(lambda: self._load_sessions(event.node, data[1]), thread=True)

    def _load_sessions(self, node, cwd: str) -> None:
        sessions = codex_data.get_project_sessions(cwd)
        self.app.call_from_thread(self._populate_sessions, node, sessions)

    def _populate_sessions(self, node, sessions) -> None:
        for child in list(node.children):
            if child.data and child.data[0] == "placeholder":
                child.remove()
        for s in sessions:
            dt = datetime.fromtimestamp(s.last_modified).strftime("%m/%d %H:%M") if s.last_modified else "?"
            summary = s.summary.replace("\n", " ")[:50] if s.summary else s.session_id[:12]
            size_kb = s.file_size / 1024
            label = f"[dim]{dt}[/]  [cyan]{escape(summary)}[/]  [dim]({size_kb:.0f}KB)[/]"
            node.add_leaf(label, data=("session", s.session_id, s.project_dir))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        if data[0] == "session":
            session_id = data[1]
            rollout_path = data[2] if len(data) > 2 else None
            self._selected = (session_id, rollout_path)
            self._selected_node = event.node
            self._render_actions()
            self.run_worker(lambda: self._load_messages(session_id, rollout_path), thread=True)
        elif data[0] == "project":
            self._selected = None
            self._selected_node = None
            self._render_actions()

    def _load_messages(self, session_id: str, rollout_path: str | None) -> None:
        messages = codex_data.get_session_messages(session_id, rollout_path, limit=50)
        self.app.call_from_thread(self._show_messages, session_id, messages)

    def _show_messages(self, session_id: str, messages: list[dict]) -> None:
        header = self.query_one("#codex-detail-header", Static)
        body = self.query_one("#codex-detail-body", Static)
        header.update(f"[bold]Session:[/] {session_id[:16]}…")
        if not messages:
            body.update(t("proj.no_messages"))
            return
        lines = []
        for m in messages:
            content = m["content"]
            if m["type"] == "user":
                lines.append(f"[bold green]User:[/]\n{escape(content)}\n")
            else:
                if len(content) > 500:
                    content = content[:500] + "…"
                lines.append(f"[bold cyan]Assistant:[/]\n{escape(content)}\n")
        body.update("\n".join(lines))

    def action_trash_session(self) -> None:
        if not self._selected:
            return
        session_id, rollout_path = self._selected
        if not rollout_path:
            return
        self.app.push_screen(
            ConfirmScreen(t("codex.confirm_trash", sid=f"{session_id[:16]}…")),
            callback=lambda ok: self._do_trash(session_id, rollout_path) if ok else None,
        )

    def _do_trash(self, session_id: str, rollout_path: str) -> None:
        node = self._selected_node

        def _work():
            ok = trash_codex_session(rollout_path)
            self.app.call_from_thread(self._on_trashed, ok, session_id, node)
        self.run_worker(_work, thread=True)

    def _on_trashed(self, ok: bool, session_id: str, node) -> None:
        if ok:
            codex_data.refresh()
            self.app.notify(t("codex.trashed", sid=f"{session_id[:12]}…"))
            self._selected = None
            if node:
                node.remove()
            self._render_actions()
        else:
            self.app.notify(t("common.failed"), severity="error")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "codex-filter":
            return
        self._filter_query = event.value.strip()
        self._build_tree()
