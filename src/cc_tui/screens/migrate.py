"""Session migration screen - two-panel folder selection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import PurePosixPath

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, RadioButton, RadioSet, Static, Tree

from cc_tui.models import PROJECTS_DIR
from cc_tui.screens.confirm import ConfirmScreen
from cc_tui.i18n import t
from cc_tui.services.migrate import get_available_projects, migrate_sessions


class MigratePane(Container):
    """Session migration with two-panel project selection."""

    CSS = """
    MigratePane {
        height: 1fr;
        padding: 1;
    }
    #migrate-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }
    #migrate-panels {
        height: 1fr;
    }
    .migrate-panel {
        width: 1fr;
        height: 1fr;
        border: tall $primary;
        padding: 0 1;
    }
    .panel-title {
        height: auto;
        text-style: bold;
        margin-bottom: 1;
    }
    .panel-selected {
        height: auto;
        margin-bottom: 1;
        color: $accent;
    }
    .migrate-tree {
        height: 1fr;
    }
    #migrate-preview {
        height: auto;
        max-height: 8;
        border-top: tall $primary;
        padding: 1;
    }
    #migrate-controls {
        height: auto;
        margin-top: 1;
        padding: 1;
    }
    #migrate-mode {
        height: auto;
        margin-bottom: 1;
    }
    #migrate-result {
        height: auto;
        margin-top: 1;
        padding: 1;
        border: round $success;
        display: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._source_hint: str | None = None
        self._source_encoded: str | None = None
        self._target_hint: str | None = None
        self._target_encoded: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(
            t("mig.info"),
            id="migrate-info",
        )
        with Horizontal(id="migrate-panels"):
            with Vertical(classes="migrate-panel"):
                yield Static(t("mig.source_title"), classes="panel-title")
                yield Static(t("mig.not_selected"), classes="panel-selected", id="source-selected")
                yield Tree("Projects", id="source-tree", classes="migrate-tree")
            with Vertical(classes="migrate-panel"):
                yield Static(t("mig.target_title"), classes="panel-title")
                yield Static(t("mig.not_selected"), classes="panel-selected", id="target-selected")
                yield Tree("Projects", id="target-tree", classes="migrate-tree")
        yield Static("", id="migrate-preview")
        with Horizontal(id="migrate-controls"):
            with RadioSet(id="migrate-mode"):
                yield RadioButton(t("mig.append"), value=True)
                yield RadioButton(t("mig.overwrite"))
            yield Button("Migrate", variant="primary", id="btn-migrate")
        yield Static("", id="migrate-result")

    def on_mount(self) -> None:
        for tree_id in ("source-tree", "target-tree"):
            tree = self.query_one(f"#{tree_id}", Tree)
            tree.show_root = False
        self.run_worker(self._load_projects, thread=True)

    def _load_projects(self) -> None:
        projects = get_available_projects()
        project_sessions = {}
        for encoded, hint in projects:
            session_dir = PROJECTS_DIR / encoded
            count = len(list(session_dir.glob("*.jsonl"))) if session_dir.exists() else 0
            project_sessions[encoded] = count
        self.app.call_from_thread(self._build_trees, projects, project_sessions)

    def _build_trees(self, projects: list[tuple[str, str]], project_sessions: dict[str, int]) -> None:
        source_tree = self.query_one("#source-tree", Tree)
        source_tree.clear()
        source_projects = [(e, h) for e, h in projects if project_sessions.get(e, 0) > 0]
        self._populate_tree(source_tree, source_projects, project_sessions)

        target_tree = self.query_one("#target-tree", Tree)
        target_tree.clear()
        self._populate_tree(target_tree, projects, project_sessions)

    def _populate_tree(self, tree: Tree, projects: list[tuple[str, str]], session_counts: dict[str, int]) -> None:
        root_nodes: dict = {}
        for encoded, hint in projects:
            parts = PurePosixPath(hint).parts
            current = root_nodes
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current["__leaf__"] = (encoded, hint, session_counts.get(encoded, 0))

        self._render_nodes(tree.root, root_nodes, "")

    def _render_nodes(self, parent, node_dict: dict, current_path: str) -> None:
        for key, children in sorted(node_dict.items()):
            if key == "__leaf__":
                continue

            new_path = f"{current_path}/{key}" if current_path else key
            is_leaf = "__leaf__" in children
            child_dirs = {k: v for k, v in children.items() if k != "__leaf__"}

            if is_leaf:
                encoded, hint, sessions = children["__leaf__"]
                name = PurePosixPath(hint).name or hint
                session_str = f"  [dim]{sessions} sessions[/]" if sessions > 0 else "  [dim]empty[/]"
                label = f"{name}{session_str}"
                if child_dirs:
                    node = parent.add(label, data=("project", hint, encoded), expand=False)
                    self._render_nodes(node, child_dirs, new_path)
                else:
                    parent.add_leaf(label, data=("project", hint, encoded))
            elif len(child_dirs) == 1:
                child_key = list(child_dirs.keys())[0]
                collapsed = f"{key}/{child_key}"
                collapsed_children = child_dirs[child_key]

                while (
                    "__leaf__" not in collapsed_children
                    and len({k for k in collapsed_children if k != "__leaf__"}) == 1
                ):
                    next_key = [k for k in collapsed_children if k != "__leaf__"][0]
                    collapsed = f"{collapsed}/{next_key}"
                    collapsed_children = collapsed_children[next_key]

                is_collapsed_leaf = "__leaf__" in collapsed_children
                collapsed_child_dirs = {k: v for k, v in collapsed_children.items() if k != "__leaf__"}

                if is_collapsed_leaf:
                    encoded, hint, sessions = collapsed_children["__leaf__"]
                    session_str = f"  [dim]{sessions} sessions[/]" if sessions > 0 else "  [dim]empty[/]"
                    label = f"{collapsed}{session_str}"
                    if collapsed_child_dirs:
                        node = parent.add(label, data=("project", hint, encoded), expand=False)
                        self._render_nodes(node, collapsed_child_dirs, f"{current_path}/{collapsed}")
                    else:
                        parent.add_leaf(label, data=("project", hint, encoded))
                elif collapsed_child_dirs:
                    count = self._count_leaves(collapsed_children)
                    group = parent.add(
                        f"[bold]{collapsed}/[/]  ({count})",
                        data=("group", None, None),
                        expand=False,
                    )
                    self._render_nodes(group, collapsed_children, f"{current_path}/{collapsed}")
            else:
                count = self._count_leaves(children)
                group = parent.add(
                    f"[bold]{key}/[/]  ({count})",
                    data=("group", None, None),
                    expand=False,
                )
                self._render_nodes(group, children, new_path)

    def _count_leaves(self, node_dict: dict) -> int:
        count = 1 if "__leaf__" in node_dict else 0
        for k, v in node_dict.items():
            if k != "__leaf__" and isinstance(v, dict):
                count += self._count_leaves(v)
        return count

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node_data = event.node.data
        if not node_data or node_data[0] != "project":
            return

        _, hint, encoded = node_data
        tree_id = event.node.tree.id

        if tree_id == "source-tree":
            self._source_hint = hint
            self._source_encoded = encoded
            self.query_one("#source-selected", Static).update(f"[bold cyan]{hint}[/]")
            self.run_worker(lambda: self._load_preview(encoded, hint), thread=True)
        elif tree_id == "target-tree":
            self._target_hint = hint
            self._target_encoded = encoded
            self.query_one("#target-selected", Static).update(f"[bold green]{hint}[/]")

    def _load_preview(self, encoded: str, hint: str) -> None:
        session_dir = PROJECTS_DIR / encoded
        if not session_dir.exists():
            self.app.call_from_thread(self._show_preview, hint, [], 0)
            return

        all_jsonl = list(session_dir.glob("*.jsonl"))
        total = len(all_jsonl)
        sessions = []
        for jsonl in sorted(all_jsonl, key=lambda f: f.stat().st_mtime, reverse=True)[:5]:
            try:
                stat = jsonl.stat()
                first_prompt = ""
                with open(jsonl) as f:
                    for line in f:
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "user" and not msg.get("isMeta"):
                                content = msg.get("message", {}).get("content", "")
                                if isinstance(content, str) and not content.startswith("<"):
                                    first_prompt = content[:80]
                                    break
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            text = block.get("text", "")
                                            if not text.startswith("<"):
                                                first_prompt = text[:80]
                                                break
                                    if first_prompt:
                                        break
                        except (json.JSONDecodeError, KeyError):
                            continue
                dt_str = datetime.fromtimestamp(stat.st_mtime).strftime("%m/%d %H:%M")
                size_kb = stat.st_size / 1024
                sessions.append(f"  {dt_str}  {first_prompt or jsonl.stem[:12]}  [dim]({size_kb:.0f}KB)[/]")
            except OSError:
                continue
        self.app.call_from_thread(self._show_preview, hint, sessions, total)

    def _show_preview(self, hint: str, sessions: list[str], total: int) -> None:
        preview = self.query_one("#migrate-preview", Static)
        if sessions:
            header = f"[bold]Source Preview:[/] {hint}  [dim]({total} sessions, showing latest 5)[/]\n"
            preview.update(header + "\n".join(sessions))
        else:
            preview.update(f"[bold]Source Preview:[/] {hint}  [dim](no sessions)[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-migrate":
            if not self._source_encoded:
                self.app.notify(t("mig.select_source"), severity="error")
                return
            if not self._target_encoded:
                self.app.notify(t("mig.select_target"), severity="error")
                return
            if self._source_encoded == self._target_encoded:
                self.app.notify(t("mig.same_error"), severity="error")
                return

            radio_set = self.query_one("#migrate-mode", RadioSet)
            mode = "append" if radio_set.pressed_index == 0 else "overwrite"

            self.app.push_screen(
                ConfirmScreen(
                    t("mig.confirm", src=self._source_hint, tgt=self._target_hint, mode=mode)
                ),
                callback=lambda ok: self._do_migrate() if ok else None,
            )

    def _do_migrate(self) -> None:
        src_hint = self._source_hint
        tgt_hint = self._target_hint
        src_enc = self._source_encoded
        tgt_enc = self._target_encoded
        mode = "append"
        radio_set = self.query_one("#migrate-mode", RadioSet)
        if radio_set.pressed_index == 1:
            mode = "overwrite"
        self.run_worker(
            lambda: self._execute_migrate(src_hint, tgt_hint, src_enc, tgt_enc, mode),
            thread=True,
        )

    def _execute_migrate(self, src_hint, tgt_hint, src_enc, tgt_enc, mode) -> None:
        result = migrate_sessions(
            source_path=src_hint,
            target_path=tgt_hint,
            mode=mode,
            source_encoded=src_enc,
            target_encoded=tgt_enc,
        )
        self.app.call_from_thread(self._show_result, result)

    def refresh_data(self) -> None:
        """Reload project trees."""
        self.run_worker(self._load_projects, thread=True)

    def _show_result(self, result) -> None:
        result_widget = self.query_one("#migrate-result", Static)
        if result.success:
            result_widget.update(
                f"[green]{t('mig.complete')}[/]\n"
                f"Sessions copied: {result.sessions_copied}\n"
                f"Memory copied: {'Yes' if result.memory_copied else 'No'}\n"
                f"{result.message}"
            )
            self.app.notify(t("mig.complete"))
            # Refresh trees to show updated session counts
            self.refresh_data()
        else:
            result_widget.update(f"[red]{t('mig.failed')}:[/] {result.message}")
            self.app.notify(t("mig.failed"), severity="error")
        result_widget.display = True
