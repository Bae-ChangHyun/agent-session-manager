"""Tests for the headless CLI subcommands (asm <command>)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from asm.__main__ import main
from tests.test_feature_smoke import _setup_fake_claude


def _run(monkeypatch, capsys, *argv: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["asm", *argv])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    return code, capsys.readouterr().out


def test_cli_sessions_search(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "sessions", "--search", "alpha")
    assert code == 0
    assert env["session_id"] in out
    assert env["other_session_id"] not in out


def test_cli_sessions_json(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "sessions", "--json")
    assert code == 0
    rows = json.loads(out)
    ids = {r["session_id"] for r in rows}
    assert {env["session_id"], env["other_session_id"]} <= ids


def test_cli_cost_json(monkeypatch, capsys, tmp_path: Path):
    _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "cost", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["claude"]["total_cost"] > 0


def test_cli_projects(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "projects")
    assert code == 0
    assert env["project_a"] in out


def test_cli_preview(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "preview", env["session_id"])
    assert code == 0
    assert "alpha prompt" in out


def test_cli_preview_missing(monkeypatch, capsys, tmp_path: Path):
    _setup_fake_claude(monkeypatch, tmp_path)
    code, _ = _run(monkeypatch, capsys, "preview", "no-such-session")
    assert code == 1


def test_cli_clean_empty_dry_run(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    # project_b's session is a single user message -> counted as empty stub.
    code, out = _run(monkeypatch, capsys, "clean", "empty", "--dry-run")
    assert code == 0
    jsonl = Path(env["projects_dir"]) / env["encoded_b"] / f"{env['other_session_id']}.jsonl"
    assert jsonl.exists()  # dry run deletes nothing


def test_cli_trash_session(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    jsonl = Path(env["projects_dir"]) / env["encoded_a"] / f"{env['session_id']}.jsonl"
    assert jsonl.exists()
    code, out = _run(monkeypatch, capsys, "trash", env["session_id"], "--yes")
    assert code == 0
    assert not jsonl.exists()


def test_cli_backup_create_and_list(monkeypatch, capsys, tmp_path: Path):
    _setup_fake_claude(monkeypatch, tmp_path)
    code, out = _run(monkeypatch, capsys, "backup", "create", "--type", "config")
    assert code == 0
    created = out.strip()
    assert Path(created).exists()
    code, out = _run(monkeypatch, capsys, "backup", "list")
    assert code == 0
    assert created in out


def test_cli_migrate(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    target = str(Path(env["home"]) / "work" / "project-gamma")
    code, out = _run(
        monkeypatch, capsys,
        "migrate", env["project_a"], target,
        "--sessions", env["session_id"], "--yes",
    )
    assert code == 0
    assert "1 session(s) copied" in out


def test_cli_destructive_requires_confirmation(monkeypatch, capsys, tmp_path: Path):
    env = _setup_fake_claude(monkeypatch, tmp_path)
    jsonl = Path(env["projects_dir"]) / env["encoded_a"] / f"{env['session_id']}.jsonl"
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    code, _ = _run(monkeypatch, capsys, "trash", env["session_id"])
    assert code == 1
    assert jsonl.exists()


def test_cli_resume_claude_dry_run(monkeypatch, capsys, tmp_path: Path):
    import os
    import shutil

    import asm.models as models

    work = tmp_path / "work" / "proj"
    work.mkdir(parents=True)
    projects = tmp_path / "projects"
    enc = models.encode_path(str(work))
    pdir = projects / enc
    pdir.mkdir(parents=True)
    sid = "aaaaaaaa-1111-2222-3333-444444444444"
    (pdir / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "cwd": str(work), "message": {"content": "hi"}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(models, "PROJECTS_DIR", projects)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")
    chdirs: list = []
    monkeypatch.setattr(os, "chdir", lambda d: chdirs.append(d))

    monkeypatch.setattr(sys, "argv", ["asm", "resume", sid, "--dry-run"])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    err = capsys.readouterr().err
    assert code == 0
    assert chdirs == [str(work)]  # cd into the recorded cwd
    assert f"claude -r {sid}" in err


def test_cli_resume_codex_dry_run(monkeypatch, capsys, tmp_path: Path):
    import os
    import shutil

    from asm.services import codex_data

    sessions = tmp_path / "sessions" / "2026" / "06" / "01"
    sessions.mkdir(parents=True)
    sid = "019ddddd-da44-7a72-8b78-912063531fae"
    cwd = str(tmp_path / "codexwork")
    (tmp_path / "codexwork").mkdir()
    (sessions / f"rollout-2026-06-01T09-00-00-{sid}.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": cwd}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "sessions")
    codex_data.refresh()
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")
    chdirs: list = []
    monkeypatch.setattr(os, "chdir", lambda d: chdirs.append(d))
    # No Claude projects dir so it falls through to Codex.
    import asm.models as models
    monkeypatch.setattr(models, "PROJECTS_DIR", tmp_path / "no-claude")

    monkeypatch.setattr(sys, "argv", ["asm", "resume", sid, "--dry-run"])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    err = capsys.readouterr().err
    assert code == 0
    assert chdirs == [cwd]
    assert f"codex resume {sid}" in err


def test_cli_resume_not_found(monkeypatch, capsys, tmp_path: Path):
    import asm.models as models
    from asm.services import codex_data

    monkeypatch.setattr(models, "PROJECTS_DIR", tmp_path / "none")
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "none2")
    code, _ = _run(monkeypatch, capsys, "resume", "no-such-id")
    assert code == 1
