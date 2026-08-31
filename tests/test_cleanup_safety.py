from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from asm.services import cleaner


def _delete(path: str) -> None:
    target = Path(path)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def _setup_cleaner(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    env_dir = claude_dir / "session-env"
    projects_dir.mkdir(parents=True)
    env_dir.mkdir()
    monkeypatch.setattr(cleaner, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(cleaner, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cleaner, "SESSION_ENV_DIR", env_dir)
    monkeypatch.setattr(cleaner, "_ALLOWED_ROOTS", (claude_dir,))
    monkeypatch.setattr(cleaner, "_TRASH_LOG", tmp_path / ".asm" / "trash-log.jsonl")
    return claude_dir, projects_dir, env_dir


def test_session_file_is_not_trashed_without_snapshot(monkeypatch, tmp_path: Path):
    _, projects_dir, _ = _setup_cleaner(monkeypatch, tmp_path)
    target = projects_dir / "project" / "session.jsonl"
    target.parent.mkdir()
    target.write_text("{}\n")
    trash_calls: list[str] = []
    monkeypatch.setattr(cleaner, "create_recovery_snapshot", lambda *_: None)
    monkeypatch.setattr(cleaner, "send2trash", trash_calls.append)

    assert cleaner.trash_single_session_file("project", "session") is False
    assert target.exists()
    assert trash_calls == []


@pytest.mark.parametrize("snapshot_id", [None, "", 0, False])
def test_cleanup_rejects_invalid_snapshot_ids(monkeypatch, tmp_path: Path, snapshot_id):
    _, projects_dir, _ = _setup_cleaner(monkeypatch, tmp_path)
    target = projects_dir / "project" / "session.jsonl"
    target.parent.mkdir()
    target.write_text("{}\n")
    monkeypatch.setattr(cleaner, "create_recovery_snapshot", lambda *_: snapshot_id)
    monkeypatch.setattr(cleaner, "send2trash", lambda path: pytest.fail(f"unexpected trash: {path}"))

    assert cleaner.trash_single_session_file("project", "session") is False
    assert target.exists()


@pytest.mark.parametrize(
    "project_encoded,session_id",
    [
        ("../projects", "session"),
        ("project", "../../history"),
        ("project", "/tmp/session"),
        (r"..\projects", "session"),
        ("project", r"..\history"),
    ],
)
def test_session_file_trash_rejects_path_traversal(
    monkeypatch, tmp_path: Path, project_encoded: str, session_id: str
):
    _, projects_dir, _ = _setup_cleaner(monkeypatch, tmp_path)
    outside = tmp_path / ".claude" / "history.jsonl"
    outside.write_text("private\n")
    monkeypatch.setattr(cleaner, "create_recovery_snapshot", lambda *_: "snapshot")
    monkeypatch.setattr(cleaner, "send2trash", lambda path: pytest.fail(f"unexpected trash: {path}"))

    assert cleaner.trash_single_session_file(project_encoded, session_id) is False
    assert outside.exists()


def test_project_session_cleanup_snapshots_every_target_before_trashing(monkeypatch, tmp_path: Path):
    _, projects_dir, env_dir = _setup_cleaner(monkeypatch, tmp_path)
    main = projects_dir / "project"
    related = env_dir / "project-worker"
    main.mkdir()
    related.mkdir()
    snapshot_calls: list[list[tuple[Path, str]]] = []
    trash_calls: list[str] = []

    def snapshots(items: list[tuple[Path, str]]):
        snapshot_calls.append(items)
        return None

    monkeypatch.setattr(cleaner, "create_recovery_snapshots", snapshots)
    monkeypatch.setattr(cleaner, "send2trash", trash_calls.append)

    assert cleaner.trash_session("project") is False
    assert main.exists()
    assert related.exists()
    assert snapshot_calls == [[(main.resolve(), "session"), (related.resolve(), "session-env")]]
    assert trash_calls == []


def test_project_session_cleanup_reports_related_partial_failure(monkeypatch, tmp_path: Path):
    _, projects_dir, env_dir = _setup_cleaner(monkeypatch, tmp_path)
    main = projects_dir / "project"
    related = env_dir / "project-worker"
    main.mkdir()
    related.mkdir()
    monkeypatch.setattr(cleaner, "create_recovery_snapshots", lambda items: ["main", "related"])

    def trash(path: str) -> None:
        if Path(path) == related.resolve():
            raise OSError("env busy")
        _delete(path)

    monkeypatch.setattr(cleaner, "send2trash", trash)

    assert cleaner.trash_session("project") is False
    assert not main.exists()
    assert related.exists()


def test_project_session_cleanup_keeps_related_data_when_main_trash_fails(monkeypatch, tmp_path: Path):
    _, projects_dir, env_dir = _setup_cleaner(monkeypatch, tmp_path)
    main = projects_dir / "project"
    related = env_dir / "project-worker"
    main.mkdir()
    related.mkdir()
    monkeypatch.setattr(cleaner, "create_recovery_snapshots", lambda items: ["main", "related"])

    def trash(path: str) -> None:
        if Path(path) == main.resolve():
            raise OSError("main busy")
        _delete(path)

    monkeypatch.setattr(cleaner, "send2trash", trash)

    assert cleaner.trash_session("project") is False
    assert main.exists()
    assert related.exists()
