"""End-to-end feature coverage for both Claude and Codex modes.

Destructive operations run against sandboxed temp dirs (send2trash is faked);
the TUI is driven headlessly through every tab in both modes.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cc_tui.app import CCTuiApp
from cc_tui.services import backup as backup_service
from cc_tui.services import claude_data, cleaner, codex_data, recovery
from cc_tui import models

from tests.test_feature_smoke import _fake_send2trash, _setup_fake_claude


# --------------------------------------------------------------------------- #
# Claude mode — service-level features not covered by the smoke test
# --------------------------------------------------------------------------- #

class TestClaudeExtraFeatures:
    def test_duplicate_sessions_detect_and_trash(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        # Put the same session id into project B as well -> duplicate.
        dup = env["session_id"]
        (env["projects_dir"] / env["encoded_b"] / f"{dup}.jsonl").write_text("{}\n")

        dups = claude_data.find_duplicate_sessions()
        assert dup in dups
        assert set(dups[dup]) == {env["encoded_a"], env["encoded_b"]}

        # Trash just the copy in project B.
        assert cleaner.trash_single_session_file(env["encoded_b"], dup) is True

    def test_remove_project_from_json(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        assert claude_data.remove_project_from_json(env["project_b"]) is True
        remaining = claude_data.get_project_paths()
        assert env["project_b"] not in remaining
        assert env["project_a"] in remaining

    def test_tasks_based_todos(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        tasks_dir = env["claude_dir"] / "tasks"
        active = env["session_id"]
        (tasks_dir / active).mkdir(parents=True)
        (tasks_dir / active / "1.json").write_text('{"subject":"do","status":"pending"}')
        (tasks_dir / "orphan-sess").mkdir()  # empty -> prunable + orphaned
        monkeypatch.setattr(claude_data, "TASKS_DIR", tasks_dir)
        monkeypatch.setattr(cleaner, "TASKS_DIR", tasks_dir)

        todos = {t.name: t for t in claude_data.get_todos()}
        assert active in todos and not todos[active].is_orphaned
        assert "orphan-sess" in todos and todos["orphan-sess"].is_orphaned
        assert cleaner.count_empty_todos() == 1
        ok, fail = cleaner.prune_empty_todo_files()
        assert ok == 1

    def test_backup_restore_roundtrip(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        cfg = backup_service.create_config_backup()
        full = backup_service.create_full_backup()
        assert cfg and full

        # Corrupt the live config, then restore it.
        env["claude_json"].write_text('{"projects": {}}')
        assert backup_service.restore_config_backup(cfg) is True
        restored = json.loads(env["claude_json"].read_text())
        assert env["project_a"] in restored.get("projects", {})

        # Full restore should rebuild the .claude dir.
        assert backup_service.restore_full_backup(full) is True
        assert (env["claude_dir"] / "projects").exists()

    def test_recovery_snapshot_and_restore(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        recovery_dir = env["home"] / ".cc-tui" / "recovery"
        monkeypatch.setattr(recovery, "RECOVERY_BASE_DIR", recovery_dir)
        monkeypatch.setattr(recovery, "CLAUDE_DIR", env["claude_dir"])
        monkeypatch.setattr(models, "RECOVERY_BASE_DIR", recovery_dir)

        target = env["debug_dir"] / f"{env['session_id']}.log"
        snap_id = recovery.create_recovery_snapshot(target, "debug")
        assert snap_id is not None
        items = recovery.list_recovery_items()
        assert any(i.id == snap_id for i in items)

        target.unlink()  # simulate deletion
        ok, _msg = recovery.restore_recovery_item(snap_id)
        assert ok is True
        assert target.exists()


# --------------------------------------------------------------------------- #
# Codex mode
# --------------------------------------------------------------------------- #

def _write_codex_rollout(path: Path, sid: str, cwd: str, model: str, first_user: str):
    rows = [
        {"type": "session_meta", "payload": {"id": sid, "timestamp": "2026-06-01T09:00:00.000Z",
                                             "cwd": cwd, "model": model, "git": {"branch": "main"}}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "input_text", "text": first_user}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                              "content": [{"type": "output_text", "text": "done"}]}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 1000, "cached_input_tokens": 100, "output_tokens": 200, "total_tokens": 1200}}}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _setup_fake_codex(monkeypatch, tmp_path) -> dict:
    codex_dir = tmp_path / ".codex"
    sessions = codex_dir / "sessions" / "2026" / "06" / "01"
    _write_codex_rollout(sessions / "rollout-a.jsonl", "aaaa", "/work/proj-a", "gpt-5.5", "first task")
    _write_codex_rollout(sessions / "rollout-b.jsonl", "bbbb", "/work/proj-b", "gpt-5", "second task")
    (codex_dir / "config.toml").write_text("x=1")
    backups_dir = tmp_path / ".cc-tui" / "backups"
    backups_dir.mkdir(parents=True)

    codex_data.refresh()
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", codex_dir / "sessions")
    monkeypatch.setattr(backup_service, "CODEX_DIR", codex_dir)
    monkeypatch.setattr(backup_service, "CODEX_SESSIONS_DIR", codex_dir / "sessions")
    monkeypatch.setattr(backup_service, "BACKUP_BASE_DIR", backups_dir)
    monkeypatch.setattr(cleaner, "CODEX_DIR", codex_dir)
    monkeypatch.setattr(cleaner, "send2trash", _fake_send2trash)
    monkeypatch.setattr(recovery, "CODEX_DIR", codex_dir)
    monkeypatch.setattr(recovery, "RECOVERY_BASE_DIR", tmp_path / ".cc-tui" / "recovery")
    return {"codex_dir": codex_dir, "sessions_dir": codex_dir / "sessions", "backups_dir": backups_dir}


class TestCodexFeatures:
    def test_projects_sessions_messages(self, monkeypatch, tmp_path):
        _setup_fake_codex(monkeypatch, tmp_path)
        assert codex_data.is_available()
        assert codex_data.total_session_count() == 2
        projects = {p.path for p in codex_data.get_projects()}
        assert projects == {"/work/proj-a", "/work/proj-b"}

        ses = codex_data.get_project_sessions("/work/proj-a")
        assert len(ses) == 1 and ses[0].session_id == "aaaa"
        msgs = codex_data.get_session_messages("aaaa", ses[0].project_dir)
        assert {m["type"] for m in msgs} == {"user", "assistant"}

    def test_dashboard_aggregations(self, monkeypatch, tmp_path):
        _setup_fake_codex(monkeypatch, tmp_path)
        usage = codex_data.get_usage_data()
        assert usage["total_cost"] > 0
        assert codex_data.get_period_usage("daily")
        assert codex_data.get_stats().total_sessions == 2

    def test_codex_backup(self, monkeypatch, tmp_path):
        _setup_fake_codex(monkeypatch, tmp_path)
        path = backup_service.create_codex_backup()
        assert path is not None
        assert (Path(path) / "sessions").exists()
        assert (Path(path) / "config.toml").exists()
        assert any(b.backup_type == "codex" for b in backup_service.list_backups())

    def test_trash_codex_session(self, monkeypatch, tmp_path):
        env = _setup_fake_codex(monkeypatch, tmp_path)
        rollout = env["sessions_dir"] / "2026" / "06" / "01" / "rollout-a.jsonl"
        assert cleaner.trash_codex_session(str(rollout)) is True
        # Outside ~/.codex must be refused.
        outside = tmp_path / "evil.jsonl"
        outside.write_text("{}")
        assert cleaner.trash_codex_session(str(outside)) is False


# --------------------------------------------------------------------------- #
# UI drive — every tab in both modes
# --------------------------------------------------------------------------- #

class TestUIBothModes:
    def test_claude_app_all_tabs(self, monkeypatch, tmp_path):
        env = _setup_fake_claude(monkeypatch, tmp_path)
        # Add a duplicate so the Projects "Duplicate Sessions" group renders.
        (env["projects_dir"] / env["encoded_b"] / f"{env['session_id']}.jsonl").write_text("{}\n")

        async def run():
            app = CCTuiApp(source="claude")
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause(); await asyncio.sleep(0.3); await pilot.pause()
                for tab in ("tab-dashboard", "tab-projects", "tab-file-history",
                            "tab-debug-todos", "tab-migrate", "tab-backups"):
                    app.action_tab(tab)
                    await pilot.pause(); await asyncio.sleep(0.2); await pilot.pause()
                # Projects tree should include the duplicate group.
                from textual.widgets import Tree
                app.action_tab("tab-projects")
                await pilot.pause(); await asyncio.sleep(0.4); await pilot.pause()
                tree = app.query_one("#project-tree", Tree)
                kinds = {c.data[0] for c in tree.root.children if c.data}
                assert "dup_group" in kinds
                app.action_refresh()
                await pilot.pause()

        asyncio.run(run())

    def test_codex_app_all_tabs(self, monkeypatch, tmp_path):
        _setup_fake_codex(monkeypatch, tmp_path)

        async def run():
            app = CCTuiApp(source="codex")
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause(); await asyncio.sleep(0.4); await pilot.pause()
                from textual.widgets import TabbedContent, Tree
                tabs = app.query_one("#main-tabs", TabbedContent)
                ids = {tp.id for tp in tabs.query("TabPane")}
                assert "tab-codex-sessions" in ids
                assert "tab-projects" not in ids  # Claude-only tab hidden
                assert "tab-migrate" not in ids

                app.action_tab("tab-codex-sessions")
                await pilot.pause(); await asyncio.sleep(0.6); await pilot.pause()
                tree = app.query_one("#codex-tree", Tree)
                projects = [c for c in tree.root.children if c.data and c.data[0] == "project"]
                assert len(projects) == 2
                projects[0].expand()
                await pilot.pause(); await asyncio.sleep(0.6); await pilot.pause()
                sessions = [c for c in projects[0].children if c.data and c.data[0] == "session"]
                assert len(sessions) >= 1

                app.action_tab("tab-backups")
                await pilot.pause(); await asyncio.sleep(0.3); await pilot.pause()
                app.action_refresh()
                await pilot.pause()

        asyncio.run(run())
