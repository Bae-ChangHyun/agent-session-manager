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
