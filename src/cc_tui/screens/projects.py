"""Projects management screen - tree with inline sessions."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static, Tree

from cc_tui.models import PROJECTS_DIR, ProjectInfo, encode_path
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.backup import create_config_backup
from cc_tui.services.claude_data import (
    get_project_sessions,
    get_projects,
    get_session_messages,
    remove_project_from_json,
)


def _fmt(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class ProjectsPane(Container):
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
    #project-detail-body {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Projects[/] - .claude.json 프로젝트 + 세션\n"
            "[dim]폴더를 펼치면 세션 목록이 보입니다. 세션을 클릭하면 대화 내용을 미리봅니다.\n"
            "[green]O[/]=폴더 존재  [red]X[/]=폴더 삭제/이동됨(설정만 남음)[/]",
            id="projects-info",
        )
        yield Button("Remove Project from Config", variant="error", id="btn-remove-project")
        with Horizontal(id="projects-layout"):
            with Vertical(id="projects-tree-panel"):
                yield Tree("Projects", id="project-tree")
            with Vertical(id="project-detail-panel"):
                yield Static("", id="project-detail-header")
                yield VerticalScroll(
                    Static("프로젝트 또는 세션을 선택하세요", id="project-detail-body"),
                    id="detail-scroll",
                )

    def on_mount(self) -> None:
        tree = self.query_one("#project-tree", Tree)
        tree.show_root = False
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_projects, thread=True)

    def _load_projects(self) -> None:
        projects = get_projects()
        self.app.call_from_thread(self._build_tree, projects)

    def _build_tree(self, projects: list[ProjectInfo]) -> None:
        tree = self.query_one("#project-tree", Tree)
        tree.clear()
        self._project_map: dict[str, ProjectInfo] = {p.path: p for p in projects}

        # Group by common prefix
        groups: dict[str, list[ProjectInfo]] = {}
        for p in projects:
            parts = PurePosixPath(p.path).parts
            depth = min(4, len(parts))
            group_key = str(PurePosixPath(*parts[:depth])) if depth >= 2 else p.path
            groups.setdefault(group_key, []).append(p)

        for group_key in sorted(groups.keys()):
            group_projects = groups[group_key]

            if len(group_projects) == 1 and group_projects[0].path == group_key:
                p = group_projects[0]
                self._add_project_node(tree.root, p, p.path)
            else:
                total_cost = sum(p.last_cost or 0 for p in group_projects)
                cost_str = f"  ${total_cost:.2f}" if total_cost > 0 else ""
                group_node = tree.root.add(
                    f"[bold]{group_key}/[/]  ({len(group_projects)}){cost_str}",
                    data=("group", group_key),
                    expand=False,
                )
                # Sub-group
                subgroups: dict[str, list[ProjectInfo]] = {}
                for p in sorted(group_projects, key=lambda x: x.path):
                    rel = p.path[len(group_key):].strip("/")
                    sub_parts = rel.split("/")
                    sub_key = sub_parts[0] if len(sub_parts) > 1 else ""
                    subgroups.setdefault(sub_key, []).append(p)

                for sub_key in sorted(subgroups.keys()):
                    sub_projects = subgroups[sub_key]
                    if sub_key and len(sub_projects) > 1:
                        sub_cost = sum(p.last_cost or 0 for p in sub_projects)
                        cost_str = f"  ${sub_cost:.2f}" if sub_cost > 0 else ""
                        sub_node = group_node.add(
                            f"[bold]{sub_key}/[/]  ({len(sub_projects)}){cost_str}",
                            data=("group", f"{group_key}/{sub_key}"),
                            expand=False,
                        )
                        for p in sorted(sub_projects, key=lambda x: x.path):
                            name = PurePosixPath(p.path).name
                            self._add_project_node(sub_node, p, name)
                    else:
                        for p in sub_projects:
                            rel = p.path[len(group_key):].strip("/") or PurePosixPath(p.path).name
                            self._add_project_node(group_node, p, rel)

    def _add_project_node(self, parent, p: ProjectInfo, display_name: str):
        """Add a project node that can be expanded to show sessions."""
        status = "[green]O[/]" if p.exists else "[red]X[/]"
        cost_str = f"  ${p.last_cost:.2f}" if p.last_cost else ""
        # Count session files
        encoded = encode_path(p.path)
        session_dir = PROJECTS_DIR / encoded
        session_count = len(list(session_dir.glob("*.jsonl"))) if session_dir.exists() else 0
        session_str = f"  [dim]{session_count} sessions[/]" if session_count > 0 else "  [dim]no sessions[/]"

        label = f"{status} {display_name}{cost_str}{session_str}"
        if session_count > 0:
            node = parent.add(label, data=("project", p.path), expand=False)
            # Add placeholder for lazy loading sessions
            node.add_leaf("[dim]Loading sessions...[/]", data=("placeholder", None))
        else:
            parent.add_leaf(label, data=("project", p.path))

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Lazy-load sessions when a project node is expanded."""
        node_data = event.node.data
        if not node_data:
            return
        kind, value = node_data
        if kind == "project" and value:
            # Check if children are just the placeholder
            children = list(event.node.children)
            if len(children) == 1 and children[0].data and children[0].data[0] == "placeholder":
                self.run_worker(lambda: self._load_sessions_for_node(event.node, value), thread=True)

    def _load_sessions_for_node(self, node, project_path: str) -> None:
        sessions = get_project_sessions(project_path)
        self.app.call_from_thread(self._populate_session_nodes, node, sessions)

    def _populate_session_nodes(self, node, sessions) -> None:
        node.remove_children()
        for s in sessions:
            ts = s.last_modified / 1000 if s.last_modified > 1e12 else s.last_modified
            dt = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts > 0 else "?"
            size_kb = s.file_size / 1024
            summary = s.summary.replace("\n", " ")[:60] if s.summary else s.session_id[:12]
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
            p = self._project_map.get(path)
            if p:
                self._show_project_detail(p)

        elif kind == "session":
            session_id = node_data[1]
            project_dir = node_data[2] if len(node_data) > 2 else None
            self.run_worker(lambda: self._load_session_messages(session_id, project_dir), thread=True)

    def _show_project_detail(self, p: ProjectInfo) -> None:
        header = self.query_one("#project-detail-header", Static)
        body = self.query_one("#project-detail-body", Static)
        status = "[green]Found[/] 폴더가 디스크에 존재" if p.exists else "[red]Missing[/] 폴더가 삭제/이동됨"
        cost = f"${p.last_cost:.4f}" if p.last_cost else "N/A"
        dur = f"{p.last_duration:.0f}s" if p.last_duration else "N/A"
        envs = len(p.session_env_dirs)
        header.update(f"[bold]{PurePosixPath(p.path).name}[/]")
        body.update(
            f"[bold]Path:[/] {p.path}\n"
            f"[bold]Status:[/] {status}\n"
            f"[bold]Cost:[/] {cost}\n"
            f"[bold]Duration:[/] {dur}\n"
            f"[bold]Session Envs:[/] {envs}"
        )

    def _load_session_messages(self, session_id: str, project_dir: str | None) -> None:
        messages = get_session_messages(session_id, limit=50)
        self.app.call_from_thread(self._show_session_messages, session_id, messages)

    def _show_session_messages(self, session_id: str, messages: list[dict]) -> None:
        header = self.query_one("#project-detail-header", Static)
        body = self.query_one("#project-detail-body", Static)
        header.update(f"[bold]Session:[/] {session_id[:16]}...")

        if not messages:
            body.update("[dim]No conversation messages found[/]")
            return

        lines = []
        for m in messages:
            role = m["type"]
            content = m["content"]
            if role == "user":
                lines.append(f"[bold green]User:[/]\n{content}\n")
            else:
                # Truncate long assistant messages
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"[bold cyan]Assistant:[/]\n{content}\n")
        body.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-remove-project":
            path = getattr(self, "_selected_project_path", None)
            if not path:
                self.app.notify("Select a project first")
                return
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
