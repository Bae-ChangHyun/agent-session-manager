"""Projects management screen - tree with inline sessions."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree

from cc_tui.models import PROJECTS_DIR, ProjectInfo, encode_path
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.backup import create_config_backup
from cc_tui.services.claude_data import (
    get_project_sessions,
    get_projects,
    get_session_messages,
    get_sessions,
    load_claude_json,
    remove_project_from_json,
)
from cc_tui.i18n import t
from cc_tui.services.cleaner import trash_sessions, trash_single_session_file
from cc_tui.widgets.action_bar import ActionBar


class ProjectsPane(Container):
    BINDINGS = [
        ("d", "trash_session", "Trash Session"),
        ("D", "trash_orphaned", "Trash Orphaned"),
        ("x", "remove_config", "Remove Config"),
    ]

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
    #projects-layout {
        height: 1fr;
    }
    #projects-tree-panel {
        width: 1fr;
        height: 1fr;
        min-width: 40;
    }
    #project-tree {
        height: 1fr;
    }
    #tree-actions {
        height: 1;
        margin-top: 1;
    }
    #project-detail-panel {
        width: 1fr;
        height: 1fr;
        border-left: tall $primary;
        padding: 0 1;
    }
    #detail-scroll {
        height: 1fr;
    }
    #project-detail-header {
        height: auto;
        text-style: bold;
        margin-bottom: 1;
    }
    #detail-actions {
        height: 1;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            t("proj.info"),
            id="projects-info",
        )
        with Horizontal(id="projects-layout"):
            with Vertical(id="projects-tree-panel"):
                yield Tree("Projects", id="project-tree")
                yield ActionBar(id="tree-actions")
            with Vertical(id="project-detail-panel"):
                yield Static("", id="project-detail-header")
                yield VerticalScroll(
                    Static(t("proj.select_hint"), id="project-detail-body"),
                    id="detail-scroll",
                )
                yield ActionBar(id="detail-actions")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_project_path: str | None = None
        self._selected_session: tuple[str, str | None] | None = None
        self._selected_session_node = None
        self._project_map: dict[str, ProjectInfo] = {}

    def on_mount(self) -> None:
        tree = self.query_one("#project-tree", Tree)
        tree.show_root = False
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_projects, thread=True)

    def _load_projects(self) -> None:
        projects = get_projects()
        orphaned_sessions = [s for s in get_sessions() if s.is_orphaned]
        self.app.call_from_thread(self._build_tree, projects, orphaned_sessions)

    def _build_tree(self, projects: list[ProjectInfo], orphaned_sessions=None) -> None:
        tree = self.query_one("#project-tree", Tree)
        tree.clear()
        self._project_map = {p.path: p for p in projects}
        all_paths = {p.path for p in projects}

        # Update orphaned sessions action bar
        self._orphaned_session_dirs = [s.dir_name for s in (orphaned_sessions or [])]
        self._render_tree_actions()

        # Build a proper tree structure by inserting each path into a nested dict
        root_nodes: dict = {}  # nested dict structure

        for p in sorted(projects, key=lambda x: x.path):
            parts = PurePosixPath(p.path).parts  # ('/', 'home', 'bch', 'Project', ...)
            current = root_nodes
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            # Mark this node as a project leaf
            current["__project__"] = p

        # Render the tree, collapsing long chains of single-child dirs
        self._render_tree_nodes(tree.root, root_nodes, "", all_paths)

    def _render_tree_actions(self) -> None:
        """Render orphaned sessions action bar below tree."""
        bar = self.query_one("#tree-actions", ActionBar)
        count = len(self._orphaned_session_dirs)
        if count > 0:
            actions = [("trash-orphaned-sessions", t("proj.btn_trash_orphaned", count=count), "#ba3c5b")]
            bar.set_actions(actions, on_action=self._handle_action)
        else:
            bar.set_actions([], on_action=self._handle_action)

    def _render_detail_actions(self, show_trash_session=False, show_remove_config=False) -> None:
        """Render detail panel action bar."""
        actions = []
        if show_trash_session:
            actions.append(("trash-session", t("proj.btn_trash_session"), "#e8890c"))
        if show_remove_config:
            actions.append(("remove-config", t("proj.btn_remove_config"), "#ba3c5b"))
        bar = self.query_one("#detail-actions", ActionBar)
        bar.set_actions(actions, on_action=self._handle_action)

    def _render_tree_nodes(self, parent_node, node_dict: dict, current_path: str, all_paths: set):
        """Recursively render tree, collapsing single-child intermediate directories."""
        for key, children in sorted(node_dict.items()):
            if key == "__project__":
                continue

            new_path = f"{current_path}/{key}" if current_path else key
            if new_path == "/":
                new_path = "/"

            is_project = "__project__" in children
            child_dirs = {k: v for k, v in children.items() if k != "__project__"}

            if is_project:
                p = children["__project__"]
                self._add_project_node(parent_node, p, key, child_dirs, all_paths)
            elif len(child_dirs) == 1 and not is_project:
                # Single child dir - collapse into parent label
                child_key = list(child_dirs.keys())[0]
                collapsed_label = f"{key}/{child_key}"
                collapsed_children = child_dirs[child_key]
                collapsed_path = f"{new_path}/{child_key}"

                # Keep collapsing while single child
                while (
                    "__project__" not in collapsed_children
                    and len({k for k in collapsed_children if k != "__project__"}) == 1
                ):
                    next_key = [k for k in collapsed_children if k != "__project__"][0]
                    collapsed_label = f"{collapsed_label}/{next_key}"
                    collapsed_children = collapsed_children[next_key]
                    collapsed_path = f"{collapsed_path}/{next_key}"

                is_collapsed_project = "__project__" in collapsed_children
                collapsed_child_dirs = {k: v for k, v in collapsed_children.items() if k != "__project__"}

                if is_collapsed_project:
                    p = collapsed_children["__project__"]
                    self._add_project_node(parent_node, p, collapsed_label, collapsed_child_dirs, all_paths)
                elif collapsed_child_dirs:
                    count = self._count_projects(collapsed_children)
                    group = parent_node.add(
                        f"[bold]{collapsed_label}/[/]  ({count})",
                        data=("group", collapsed_path),
                        expand=False,
                    )
                    self._render_tree_nodes(group, collapsed_children, collapsed_path, all_paths)
            else:
                # Multiple children - create group node
                count = self._count_projects(children)
                group = parent_node.add(
                    f"[bold]{key}/[/]  ({count})",
                    data=("group", new_path),
                    expand=False,
                )
                self._render_tree_nodes(group, children, new_path, all_paths)

    def _count_projects(self, node_dict: dict) -> int:
        """Count total project leaves in a subtree."""
        count = 1 if "__project__" in node_dict else 0
        for k, v in node_dict.items():
            if k != "__project__" and isinstance(v, dict):
                count += self._count_projects(v)
        return count

    def _add_project_node(self, parent, p: ProjectInfo, display_name: str, child_dirs: dict, all_paths: set):
        """Add a project node that can be expanded to show sessions."""
        status = "[green]O[/]" if p.exists else "[red]X[/]"
        encoded = encode_path(p.path)
        session_dir = PROJECTS_DIR / encoded
        session_count = len(list(session_dir.glob("*.jsonl"))) if session_dir.exists() else 0
        session_str = f"  [dim]{session_count} sessions[/]" if session_count > 0 else ""

        label = f"{status} {display_name}{session_str}"

        if session_count > 0 or child_dirs:
            node = parent.add(label, data=("project", p.path), expand=False)
            if session_count > 0:
                node.add_leaf("[dim]...[/]", data=("placeholder", None))
            # Add child dirs if any
            if child_dirs:
                self._render_tree_nodes(node, {k: v for k, v in child_dirs.items()}, p.path, all_paths)
        else:
            parent.add_leaf(label, data=("project", p.path))

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node_data = event.node.data
        if not node_data:
            return
        kind, value = node_data[0], node_data[1] if len(node_data) > 1 else None
        if kind == "project" and value:
            children = list(event.node.children)
            if any(c.data and c.data[0] == "placeholder" for c in children):
                self.run_worker(lambda: self._load_sessions(event.node, value), thread=True)

    def _load_sessions(self, node, project_path: str) -> None:
        sessions = get_project_sessions(project_path)
        self.app.call_from_thread(self._populate_sessions, node, sessions)

    def _populate_sessions(self, node, sessions) -> None:
        # Remove placeholder
        for child in list(node.children):
            if child.data and child.data[0] == "placeholder":
                child.remove()
        for s in sessions:
            ts = s.last_modified / 1000 if s.last_modified > 1e12 else s.last_modified
            dt = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts > 0 else "?"
            size_kb = s.file_size / 1024
            summary = s.summary.replace("\n", " ")[:50] if s.summary else s.session_id[:12]
            label = f"[dim]{dt}[/]  [cyan]{summary}[/]  [dim]({size_kb:.0f}KB)[/]"
            node.add_leaf(label, data=("session", s.session_id, s.project_dir))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node_data = event.node.data
        if not node_data:
            return
        kind = node_data[0]

        if kind == "project":
            path = node_data[1]
            self._selected_project_path = path
            self._selected_session = None
            self._selected_session_node = None
            encoded = encode_path(path)
            session_dir = PROJECTS_DIR / encoded
            session_count = len(list(session_dir.glob("*.jsonl"))) if session_dir.exists() else 0
            self._render_detail_actions(
                show_trash_session=False,
                show_remove_config=(session_count == 0),
            )
            p = self._project_map.get(path)
            if p:
                self._show_project_detail(p, session_count)
        elif kind == "session":
            session_id = node_data[1]
            project_dir = node_data[2] if len(node_data) > 2 else None
            self._selected_session = (session_id, project_dir)
            self._selected_session_node = event.node
            self._render_detail_actions(
                show_trash_session=True,
                show_remove_config=False,
            )
            self.run_worker(lambda: self._load_messages(session_id, project_dir), thread=True)

    def _show_project_detail(self, p: ProjectInfo, session_count: int = 0) -> None:
        header = self.query_one("#project-detail-header", Static)
        body = self.query_one("#project-detail-body", Static)
        status = t("proj.status_found") if p.exists else t("proj.status_missing")
        header.update(f"[bold]{PurePosixPath(p.path).name}[/]")

        detail = (
            f"[bold]Path:[/] {p.path}\n"
            f"[bold]Status:[/] {status}\n"
            f"[bold]Sessions:[/] {session_count}개\n"
        )

        # Config 내용 표시
        config_data = load_claude_json().get("projects", {}).get(p.path, {})
        if config_data:
            detail += "\n[bold]Config:[/]\n"
            cost = config_data.get("lastCost")
            if cost is not None:
                detail += f"  Last Cost: ${cost:.4f}\n"
            duration = config_data.get("lastDuration")
            if duration:
                detail += f"  Last Duration: {duration / 1000:.1f}s\n"
            last_sid = config_data.get("lastSessionId", "")
            if last_sid:
                detail += f"  Last Session: {last_sid[:12]}...\n"
            mcp = config_data.get("mcpServers", {})
            if mcp:
                detail += f"  MCP Servers: {', '.join(mcp.keys())}\n"
            tools = config_data.get("allowedTools", [])
            if tools:
                detail += f"  Allowed Tools: {len(tools)}개\n"
            model_usage = config_data.get("lastModelUsage", {})
            if model_usage:
                for model, usage in model_usage.items():
                    short = model.replace("claude-", "").split("-2025")[0].split("-2026")[0]
                    detail += f"  Model: {short} (${usage.get('costUSD', 0):.2f})\n"

        if session_count > 0:
            detail += f"\n{t('proj.sessions_hint')}"
        else:
            detail += f"\n{t('proj.no_sessions_hint')}"
        body.update(detail)

    def _load_messages(self, session_id: str, project_dir: str | None) -> None:
        messages = get_session_messages(session_id, limit=50)
        self.app.call_from_thread(self._show_messages, session_id, messages)

    def _show_messages(self, session_id: str, messages: list[dict]) -> None:
        header = self.query_one("#project-detail-header", Static)
        body = self.query_one("#project-detail-body", Static)
        header.update(f"[bold]Session:[/] {session_id[:16]}...")

        if not messages:
            body.update(t("proj.no_messages"))
            return

        lines = []
        for m in messages:
            content = m["content"]
            if m["type"] == "user":
                lines.append(f"[bold green]User:[/]\n{content}\n")
            else:
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"[bold cyan]Assistant:[/]\n{content}\n")
        body.update("\n".join(lines))

    def action_trash_session(self) -> None:
        self._handle_action("trash-session")

    def action_trash_orphaned(self) -> None:
        self._handle_action("trash-orphaned-sessions")

    def action_remove_config(self) -> None:
        self._handle_action("remove-config")

    def _handle_action(self, action_id: str) -> None:
        if action_id == "trash-session":
            session = getattr(self, "_selected_session", None)
            if not session:
                return
            session_id, project_dir = session
            self.app.push_screen(
                ConfirmScreen(
                    t("proj.confirm_trash_session", sid=f"{session_id[:16]}...")
                ),
                callback=lambda ok: self._do_trash_session() if ok else None,
            )
        elif action_id == "remove-config":
            path = getattr(self, "_selected_project_path", None)
            if not path:
                return
            self.app.push_screen(
                ConfirmScreen(
                    t("proj.confirm_remove_config", path=path)
                ),
                callback=lambda ok: self._do_remove_config(path) if ok else None,
            )
        elif action_id == "trash-orphaned-sessions":
            names = getattr(self, "_orphaned_session_dirs", [])
            if not names:
                self.app.notify(t("common.no_items"))
                return
            self.app.push_screen(
                ConfirmScreen(t("proj.confirm_trash_orphaned", count=len(names))),
                callback=lambda ok: self._do_trash_orphaned_sessions() if ok else None,
            )

    def _do_trash_session(self) -> None:
        session = getattr(self, "_selected_session", None)
        if not session:
            return
        session_id, project_dir = session
        if not project_dir:
            self.app.notify(t("proj.no_dir_info"), severity="error")
            return
        if trash_single_session_file(project_dir, session_id):
            self.app.notify(t("proj.trash_ok", sid=f"{session_id[:12]}..."))
            self._selected_session = None
            # Remove node from tree without full rebuild
            node = getattr(self, "_selected_session_node", None)
            if node:
                parent = node.parent
                node.remove()
                # Update parent project label's session count
                if parent and parent.data and parent.data[0] == "project":
                    session_dir = PROJECTS_DIR / project_dir
                    new_count = len(list(session_dir.glob("*.jsonl"))) if session_dir.exists() else 0
                    p_path = parent.data[1]
                    p = self._project_map.get(p_path)
                    if p:
                        status = "[green]O[/]" if p.exists else "[red]X[/]"
                        name = PurePosixPath(p_path).name
                        count_str = f"  [dim]{new_count} sessions[/]" if new_count > 0 else ""
                        parent.set_label(f"{status} {name}{count_str}")
            self._render_detail_actions(show_trash_session=False, show_remove_config=False)
        else:
            self.app.notify(t("proj.trash_fail"), severity="error")

    def _do_remove_config(self, path: str) -> None:
        create_config_backup()
        if remove_project_from_json(path):
            self.app.notify(t("proj.config_removed", path=path))
            # Full rebuild needed since project is gone from config
            self.refresh_data()
        else:
            self.app.notify(t("proj.config_fail"), severity="error")

    def _do_trash_orphaned_sessions(self) -> None:
        names = getattr(self, "_orphaned_session_dirs", [])
        ok, fail = trash_sessions(names)
        self.app.notify(t("common.trash_bulk_ok", ok=ok, fail=fail))
        self.refresh_data()
