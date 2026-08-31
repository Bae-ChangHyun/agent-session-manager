"""End-to-end TUI interaction tests — real app, real key/action flows.

The migrate-tab corruption shipped because service-level tests were thorough
while the TUI interaction layer (key bindings, confirm dialogs, state after
actions) was only smoke-tested. These tests drive each tab's destructive and
stateful flows the way a user does.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from asm.app import CCTuiApp
from tests.async_utils import run_async_test
from tests.test_feature_smoke import _setup_fake_claude


def _run_app(coro_body):
    async def run():
        app = CCTuiApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.6)
            await pilot.pause()
            await coro_body(app, pilot)
        return app

    return run_async_test(run())


# ── Dashboard ────────────────────────────────────────────────────────────


def test_dashboard_source_and_period_keys(monkeypatch, tmp_path: Path):
    _setup_fake_claude(monkeypatch, tmp_path)
    # Give the dashboard a Codex source too — cycling is (intentionally) a
    # no-op when only Claude data exists.
    from asm.services import codex_data
    from tests.test_codex_data import _write_rollout_real_layout
    codex_root = tmp_path / "codex-sessions"
    _write_rollout_real_layout(
        codex_root / "2026" / "07" / "01" / "rollout-2026-07-01T09-00-00-e2e1.jsonl",
        "e2e1", "/work/e2e", ["gpt-5.5"],
        {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 10, "total_tokens": 1010},
    )
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", codex_root)
    codex_data.refresh()

    async def body(app, pilot):
        dash = app.query_one("DashboardPane")
        assert dash._source == "all"
        dash.action_source_cycle()
        assert dash._source == "claude"
        dash.action_source_cycle()
        assert dash._source == "codex"
        dash.action_period("weekly")
        assert dash._period == "weekly"
        dash.action_period_next()
        assert dash._period == "monthly"
        dash.action_period_prev()
        assert dash._period == "weekly"
        # Header renders the active rate source (never blank/crashing).
        from textual.widgets import Static
        header = app.query_one("#dash-header", Static)
        assert "rates:" in str(header.render())

    _run_app(body)


# ── Projects: trash via confirm dialog, export, remove-config ───────────


def test_projects_trash_session_flow(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    jsonl = Path(env["projects_dir"]) / env["encoded_a"] / f"{env['session_id']}.jsonl"

    async def body(app, pilot):
        pane = app.query_one("ProjectsPane")
        # Selection state normally set when the user clicks a session row.
        pane._selected_session = (env["session_id"], env["encoded_a"], "claude")
        pane.action_trash_session()
        await pilot.pause()
        assert len(app.screen_stack) == 2, "confirm dialog must appear"
        await pilot.press("y")
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        assert not jsonl.exists(), "session file should be trashed after confirm"

    _run_app(body)


def test_projects_trash_session_cancel_keeps_file(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    jsonl = Path(env["projects_dir"]) / env["encoded_a"] / f"{env['session_id']}.jsonl"

    async def body(app, pilot):
        pane = app.query_one("ProjectsPane")
        pane._selected_session = (env["session_id"], env["encoded_a"], "claude")
        pane.action_trash_session()
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert jsonl.exists(), "cancel must not delete anything"

    _run_app(body)


def test_projects_export_session_markdown(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)

    async def body(app, pilot):
        pane = app.query_one("ProjectsPane")
        pane._preview_export = (env["session_id"], "claude", env["encoded_a"])
        pane.action_export_session()
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        home = Path(env["home"])
        exports = list(home.glob("asm-session-*.md")) + list((home / "Desktop").glob("asm-session-*.md"))
        assert exports, "export should write a markdown file"
        text = exports[0].read_text()
        assert "alpha prompt" in text and "alpha answer" in text

    _run_app(body)


# ── File History / Debug-Todos: orphan cleanup flows ────────────────────


def test_file_history_trash_orphaned_flow(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    orphan = Path(env["file_history_dir"]) / "orphaned-session"

    async def body(app, pilot):
        app.action_tab("tab-file-history")
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        pane = app.query_one("FileHistoryPane")
        pane.action_trash_orphaned()
        await pilot.pause()
        if len(app.screen_stack) == 2:  # confirm dialog
            await pilot.press("y")
            await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        assert not orphan.exists(), "orphaned file-history dir should be trashed"

    _run_app(body)


def test_debug_todos_prune_empty_flow(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    empty_debug = Path(env["debug_dir"]) / "orphaned.log"  # content "[]"
    full_debug = Path(env["debug_dir"]) / f"{env['session_id']}.log"

    async def body(app, pilot):
        app.action_tab("tab-debug-todos")
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        pane = app.query_one("DebugTodosPane")
        pane._handle_action("prune-debug")  # same path as the ActionBar button
        await pilot.pause()
        if len(app.screen_stack) == 2:
            await pilot.press("y")
            await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        assert not empty_debug.exists(), "empty debug file should be pruned"
        assert full_debug.exists(), "non-empty debug file must survive"

    _run_app(body)


# ── Backups tab: create through the UI handler ──────────────────────────


def test_backups_config_create_via_ui(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)

    async def body(app, pilot):
        app.action_tab("tab-backups")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()
        pane = app.query_one("BackupsPane")
        pane._handle_action("config-backup")
        await asyncio.sleep(0.5)
        await pilot.pause()
        config_backups = list((Path(env["backups_dir"]) / "config").glob("*.json"))
        assert config_backups, "config backup should be created from the UI action"

    _run_app(body)


# ── Artifacts tab: list / open / copy ────────────────────────────────────


def _write_artifact_session(projects_dir: Path, encoded: str) -> str:
    url = "https://claude.ai/code/artifact/e2e-test-111"
    rows = [
        {"type": "assistant", "timestamp": "2026-07-20T08:00:00Z",
         "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Artifact",
                                  "input": {"file_path": "/tmp/x.html", "title": "E2E Page"}}]}},
        {"type": "user", "timestamp": "2026-07-20T08:00:01Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                  "content": f"Published /tmp/x.html at {url}"}]}},
    ]
    f = projects_dir / encoded / "artifact-e2e.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return url


def test_artifacts_tab_lists_and_opens(monkeypatch, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    from asm.services import artifacts as artifacts_service
    monkeypatch.setattr(artifacts_service, "PROJECTS_DIR", Path(env["projects_dir"]))
    url = _write_artifact_session(Path(env["projects_dir"]), env["encoded_a"])

    opened: list[str] = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u))

    async def body(app, pilot):
        app.action_tab("tab-artifacts")
        await pilot.pause()
        await asyncio.sleep(0.5)
        await pilot.pause()
        pane = app.query_one("ArtifactsPane")
        assert [a.url for a in pane._artifacts] == [url]
        pane.action_open_artifact()
        assert opened == [url]
        copied: list[str] = []
        monkeypatch.setattr(app, "copy_to_clipboard", lambda t: copied.append(t))
        pane.action_copy_url()
        assert copied == [url]

    _run_app(body)
