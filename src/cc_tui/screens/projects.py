"""Projects management screen - tree view grouped by directory hierarchy."""

from __future__ import annotations

from pathlib import PurePosixPath

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Static, Tree

from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.backup import create_config_backup
from cc_tui.services.claude_data import get_projects, remove_project_from_json
from cc_tui.models import ProjectInfo


class ProjectsPane(Container):
    """View and manage projects from .claude.json in a tree layout."""

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
        width: 2fr;
        height: 1fr;
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
    #project-detail {
        height: auto;
    }
    .detail-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Projects[/] - .claude.json에 등록된 프로젝트 목록\n"
            "[dim]상위 폴더별로 그룹핑됩니다. 프로젝트를 선택하면 상세 정보를 확인할 수 있습니다.[/]",
            id="projects-info",
        )
        yield Button("Remove Selected from Config", variant="error", id="btn-remove-projects")
        with Horizontal(id="projects-layout"):
            with Vertical(id="projects-tree-panel"):
                yield Tree("Projects", id="project-tree")
            with Vertical(id="project-detail-panel"):
                yield Static("Project Detail", classes="detail-title")
                yield Static("Select a project to view details", id="project-detail")

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

        # Build hierarchical structure
        # Group by common path prefixes (2-3 levels deep)
        groups: dict[str, list[ProjectInfo]] = {}
        for p in projects:
            parts = PurePosixPath(p.path).parts
            # Use first 3 parts as group key (e.g., /home/user/Projects)
            if len(parts) >= 4:
                group_key = str(PurePosixPath(*parts[:4]))
            elif len(parts) >= 3:
                group_key = str(PurePosixPath(*parts[:3]))
            else:
                group_key = str(PurePosixPath(*parts[:2])) if len(parts) >= 2 else "/"
            groups.setdefault(group_key, []).append(p)

        # Sort groups, then build tree nodes
        for group_key in sorted(groups.keys()):
            group_projects = groups[group_key]
            if len(group_projects) == 1 and group_projects[0].path == group_key:
                # Single project at this level, show directly
                p = group_projects[0]
                label = self._make_project_label(p)
                tree.root.add_leaf(label, data=p.path)
            else:
                # Group node
                group_node = tree.root.add(
                    f"[bold]{group_key}/[/]  ({len(group_projects)})",
                    data=None,
                    expand=False,
                )
                # Sub-group by next level
                subgroups: dict[str, list[ProjectInfo]] = {}
                for p in sorted(group_projects, key=lambda x: x.path):
                    rel = p.path[len(group_key):].strip("/")
                    sub_parts = rel.split("/")
                    if len(sub_parts) > 1:
                        sub_key = sub_parts[0]
                    else:
                        sub_key = ""
                    subgroups.setdefault(sub_key, []).append(p)

                for sub_key in sorted(subgroups.keys()):
                    sub_projects = subgroups[sub_key]
                    if sub_key and len(sub_projects) > 1:
                        sub_node = group_node.add(
                            f"[bold]{sub_key}/[/]  ({len(sub_projects)})",
                            data=None,
                            expand=False,
                        )
                        for p in sorted(sub_projects, key=lambda x: x.path):
                            name = PurePosixPath(p.path).name
                            label = self._make_leaf_label(p, name)
                            sub_node.add_leaf(label, data=p.path)
                    else:
                        for p in sub_projects:
                            rel_name = p.path[len(group_key):].strip("/")
                            label = self._make_leaf_label(p, rel_name or PurePosixPath(p.path).name)
                            group_node.add_leaf(label, data=p.path)

    def _make_project_label(self, p: ProjectInfo) -> str:
        status = "[green]O[/]" if p.exists else "[red]X[/]"
        return f"{status} {p.path}"

    def _make_leaf_label(self, p: ProjectInfo, name: str) -> str:
        status = "[green]O[/]" if p.exists else "[red]X[/]"
        return f"{status} {name}"

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Show project detail when a leaf node is selected."""
        path = event.node.data
        if path and path in self._project_map:
            p = self._project_map[path]
            self._selected_path = path
            status = "[green]Found - 폴더가 디스크에 존재합니다[/]" if p.exists else "[red]Missing - 폴더가 삭제/이동되었습니다[/]"
            cost = f"${p.last_cost:.4f}" if p.last_cost else "N/A"
            duration = f"{p.last_duration:.0f}s" if p.last_duration else "N/A"
            envs = ", ".join(p.session_env_dirs) if p.session_env_dirs else "None"

            detail = (
                f"[bold]Path:[/] {p.path}\n\n"
                f"[bold]Status:[/] {status}\n\n"
                f"[bold]Last Cost:[/] {cost}\n"
                f"[bold]Duration:[/] {duration}\n\n"
                f"[bold]Session Envs:[/] {len(p.session_env_dirs)}\n"
                f"{envs}"
            )
            self.query_one("#project-detail", Static).update(detail)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-remove-projects":
            path = getattr(self, "_selected_path", None)
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
