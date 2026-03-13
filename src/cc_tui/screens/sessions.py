"""Sessions management screen - tree view with preview."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static, Tree

from cc_tui.models import PROJECTS_DIR
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.services.claude_data import get_session_messages, get_sessions
from cc_tui.services.cleaner import trash_session


class SessionsPane(Container):
    """View and manage session data with tree layout."""

    CSS = """
    SessionsPane {
        height: 1fr;
        padding: 1;
    }
    #sessions-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #sessions-layout {
        height: 1fr;
    }
    #sessions-tree-panel {
        width: 1fr;
        height: 1fr;
    }
    #session-tree {
        height: 1fr;
    }
    #sessions-preview-panel {
        width: 1fr;
        height: 1fr;
        border-left: tall $primary;
        padding: 0 1;
    }
    #session-detail-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #session-messages {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Sessions[/] - 실제 대화 기록 파일 (JSONL)\n"
            "[dim]~/.claude/projects/ 아래에 프로젝트별로 세션이 저장됩니다. "
            "세션을 선택하면 대화 내용을 미리볼 수 있습니다.[/]",
            id="sessions-info",
        )
        yield Button("Trash Selected Session Dir", variant="error", id="btn-trash-session")
        with Horizontal(id="sessions-layout"):
            with Vertical(id="sessions-tree-panel"):
                yield Tree("Sessions", id="session-tree")
            with Vertical(id="sessions-preview-panel"):
                yield Static("Session Preview", id="session-detail-title")
                yield VerticalScroll(
                    Static("Select a session to preview", id="session-preview"),
                    id="session-messages",
                )

    def on_mount(self) -> None:
        tree = self.query_one("#session-tree", Tree)
        tree.show_root = False
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_sessions, thread=True)

    def _load_sessions(self) -> None:
        sessions = get_sessions()
        self.app.call_from_thread(self._build_tree, sessions)

    def _build_tree(self, sessions) -> None:
        tree = self.query_one("#session-tree", Tree)
        tree.clear()
        self._session_map = {}

        # Decode encoded dir names back to paths for grouping
        decoded: list[tuple[str, str, object]] = []  # (decoded_path, dir_name, session)
        for s in sessions:
            # Encoded name like -home-bch-Project-sub-project-...
            parts = s.dir_name.strip("-").split("-")
            path_hint = "/" + "/".join(p for p in parts if p)
            decoded.append((path_hint, s.dir_name, s))
            self._session_map[s.dir_name] = s

        # Group by first 3-4 path components
        groups: dict[str, list[tuple[str, str, object]]] = {}
        for path_hint, dir_name, s in sorted(decoded, key=lambda x: x[0]):
            path_parts = PurePosixPath(path_hint).parts
            if len(path_parts) >= 4:
                group_key = str(PurePosixPath(*path_parts[:4]))
            elif len(path_parts) >= 3:
                group_key = str(PurePosixPath(*path_parts[:3]))
            else:
                group_key = path_hint
            groups.setdefault(group_key, []).append((path_hint, dir_name, s))

        for group_key in sorted(groups.keys()):
            items = groups[group_key]
            if len(items) == 1:
                path_hint, dir_name, s = items[0]
                label = self._make_session_label(path_hint, s)
                tree.root.add_leaf(label, data=dir_name)
            else:
                orphaned_count = sum(1 for _, _, s in items if s.is_orphaned)
                group_label = f"[bold]{group_key}/[/]  ({len(items)}"
                if orphaned_count:
                    group_label += f", [red]{orphaned_count} orphaned[/]"
                group_label += ")"

                group_node = tree.root.add(group_label, data=None, expand=False)

                # Sub-group by next level
                subgroups: dict[str, list[tuple[str, str, object]]] = {}
                for path_hint, dir_name, s in items:
                    rel = path_hint[len(group_key):].strip("/")
                    sub_parts = rel.split("/")
                    sub_key = sub_parts[0] if len(sub_parts) > 1 else ""
                    subgroups.setdefault(sub_key, []).append((path_hint, dir_name, s))

                for sub_key in sorted(subgroups.keys()):
                    sub_items = subgroups[sub_key]
                    if sub_key and len(sub_items) > 1:
                        sub_node = group_node.add(
                            f"[bold]{sub_key}/[/]  ({len(sub_items)})",
                            data=None,
                            expand=False,
                        )
                        for path_hint, dir_name, s in sub_items:
                            name = PurePosixPath(path_hint).name
                            label = self._make_leaf_label(name, s)
                            sub_node.add_leaf(label, data=dir_name)
                    else:
                        for path_hint, dir_name, s in sub_items:
                            rel = path_hint[len(group_key):].strip("/")
                            label = self._make_leaf_label(rel or PurePosixPath(path_hint).name, s)
                            group_node.add_leaf(label, data=dir_name)

    def _make_session_label(self, path_hint: str, s) -> str:
        orphaned = " [red](orphaned)[/]" if s.is_orphaned else ""
        return f"{path_hint}  [dim]({s.file_count} files)[/]{orphaned}"

    def _make_leaf_label(self, name: str, s) -> str:
        orphaned = " [red](orphaned)[/]" if s.is_orphaned else ""
        return f"{name}  [dim]({s.file_count} files)[/]{orphaned}"

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        dir_name = event.node.data
        if dir_name and dir_name in self._session_map:
            self._selected_dir = dir_name
            self.run_worker(lambda: self._load_preview(dir_name), thread=True)

    def _load_preview(self, dir_name: str) -> None:
        session_dir = PROJECTS_DIR / dir_name
        jsonl_files = sorted(session_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True) if session_dir.exists() else []

        if not jsonl_files:
            self.app.call_from_thread(self._show_preview, dir_name, "No session files found", [])
            return

        # Show info about all sessions in this dir
        session_info_lines = [f"[bold]{len(jsonl_files)} session(s) in this directory[/]\n"]

        # Preview the most recent session
        latest = jsonl_files[0]
        session_id = latest.stem
        messages = get_session_messages(session_id, limit=20)

        for i, f in enumerate(jsonl_files[:5]):
            size_kb = f.stat().st_size / 1024
            marker = " [cyan]<< previewing[/]" if i == 0 else ""
            session_info_lines.append(f"  {f.stem[:12]}...  ({size_kb:.0f} KB){marker}")

        if len(jsonl_files) > 5:
            session_info_lines.append(f"  ... and {len(jsonl_files) - 5} more")

        header = "\n".join(session_info_lines)
        self.app.call_from_thread(self._show_preview, dir_name, header, messages)

    def _show_preview(self, dir_name: str, header: str, messages: list[dict]) -> None:
        title = self.query_one("#session-detail-title", Static)
        title.update(f"Session Dir: {dir_name[:50]}")
        preview = self.query_one("#session-preview", Static)

        lines = [header, "\n[bold]--- Latest Session Preview ---[/]\n"]
        if messages:
            for m in messages[-10:]:
                role = "User" if m["type"] == "user" else "Assistant"
                content = m["content"][:300].replace("\n", " ")
                color = "green" if m["type"] == "user" else "cyan"
                lines.append(f"[{color}]{role}:[/] {content}\n")
        else:
            lines.append("[dim]No messages to preview[/]")

        preview.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-trash-session":
            dir_name = getattr(self, "_selected_dir", None)
            if not dir_name:
                self.app.notify("Select a session first")
                return
            self.app.push_screen(
                ConfirmScreen(
                    f"Move to trash?\n\n"
                    f"Directory: {dir_name}\n"
                    f"This will also remove related session-env dirs."
                ),
                callback=lambda ok: self._do_trash(dir_name) if ok else None,
            )

    def _do_trash(self, dir_name: str) -> None:
        if trash_session(dir_name):
            self.app.notify(f"Trashed: {dir_name}")
            self._selected_dir = None
            self.refresh_data()
        else:
            self.app.notify("Failed to trash", severity="error")
