"""Regression tests for session migration (path rewrite scope, selection UX)."""

from __future__ import annotations

import json
from pathlib import Path

from asm.services import migrate
from tests.async_utils import run_async_test

SRC = "/home/me"
TGT = "/home/me/work/proj"  # source path is a prefix of the target — the
                            # combination that turned repeated rewrites into
                            # nested paths before the fix


def _write_session(path: Path, sid: str, cwd: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "cwd": cwd, "message": {"content": "hi"}}) + "\n"
    )


def _cwd_of(path: Path) -> str:
    return json.loads(path.read_text().splitlines()[0])["cwd"]


def _setup_dirs(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    projects = tmp_path / "projects"
    monkeypatch.setattr(migrate, "PROJECTS_DIR", projects)
    src_dir = projects / migrate.encode_path(SRC)
    tgt_dir = projects / migrate.encode_path(TGT)
    return src_dir, tgt_dir


def test_repeat_migrate_does_not_renest_paths(monkeypatch, tmp_path: Path):
    src_dir, tgt_dir = _setup_dirs(monkeypatch, tmp_path)
    _write_session(src_dir, "s1", SRC)

    r1 = migrate.migrate_sessions(SRC, TGT)
    assert r1.success and r1.sessions_copied == 1
    assert _cwd_of(tgt_dir / "s1.jsonl") == TGT

    # Second run: s1 already in target → skipped, and crucially NOT rewritten
    # again (the old code re-applied the replace to every target file).
    r2 = migrate.migrate_sessions(SRC, TGT)
    assert r2.sessions_copied == 0
    assert r2.sessions_skipped == 1
    assert _cwd_of(tgt_dir / "s1.jsonl") == TGT

    # A later run copying a new session still leaves earlier copies alone.
    _write_session(src_dir, "s2", SRC)
    r3 = migrate.migrate_sessions(SRC, TGT)
    assert r3.sessions_copied == 1 and r3.sessions_skipped == 1
    assert _cwd_of(tgt_dir / "s1.jsonl") == TGT
    assert _cwd_of(tgt_dir / "s2.jsonl") == TGT


def test_migrate_leaves_native_target_sessions_untouched(monkeypatch, tmp_path: Path):
    src_dir, tgt_dir = _setup_dirs(monkeypatch, tmp_path)
    _write_session(src_dir, "incoming", SRC)
    # A session that was born in the target project (its cwd contains the
    # source path as a prefix — the old rewrite corrupted exactly these).
    _write_session(tgt_dir, "native", TGT)

    result = migrate.migrate_sessions(SRC, TGT)
    assert result.success
    assert _cwd_of(tgt_dir / "native.jsonl") == TGT
    assert _cwd_of(tgt_dir / "incoming.jsonl") == TGT


def test_migrate_pane_defaults_to_no_selection(monkeypatch, tmp_path: Path):
    from asm.app import CCTuiApp
    from tests.test_feature_smoke import _setup_fake_claude

    _setup_fake_claude(monkeypatch, tmp_path)

    async def run():
        app = CCTuiApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            pane = app.query_one("MigratePane")
            pane._source_hint = "/x"
            pane._populate_session_table("/x", [
                ("sid-1", "07/24 10:00", "first", "1KB"),
                ("sid-2", "07/24 11:00", "second", "2KB"),
            ])
            assert pane._selected_sessions == set()  # nothing pre-checked
            pane.action_toggle_all()
            assert pane._selected_sessions == {"sid-1", "sid-2"}
            pane.action_toggle_all()
            assert pane._selected_sessions == set()
            # No selection → migrate refuses before showing any dialog.
            pane._source_encoded = "-x"
            pane._target_encoded = "-y"
            pane._target_hint = "/y"
            pane._start_migrate()
            await pilot.pause()
            assert len(app.screen_stack) == 1  # no confirm screen pushed

    run_async_test(run())
