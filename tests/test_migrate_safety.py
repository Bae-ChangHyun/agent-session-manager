from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from asm.services import migrate
from tests.async_utils import run_async_test


def _session(path: Path, session_id: str, cwd: str, extra: str = "") -> None:
    path.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"type": "user", "cwd": cwd, "message": {"content": "hi"}}) + "\n"
    (path / f"{session_id}.jsonl").write_text(content + extra)


def _projects(monkeypatch, tmp_path: Path) -> Path:
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(migrate, "PROJECTS_DIR", projects)
    monkeypatch.setattr(migrate.models, "CLAUDE_JSON", tmp_path / ".claude.json")
    return projects


def _snapshot(path: Path) -> dict[str, tuple[str, bytes | str]]:
    result = {}
    if not path.exists():
        return result
    for item in sorted(path.rglob("*")):
        relative = str(item.relative_to(path))
        if item.is_symlink():
            result[relative] = ("symlink", str(item.readlink()))
        elif item.is_dir():
            result[relative] = ("dir", "")
        else:
            result[relative] = ("file", item.read_bytes())
    return result


@pytest.mark.parametrize("source", ["/work/my-project", "/work/my_project", "/work/my.project"])
def test_available_projects_uses_recorded_source_path(monkeypatch, tmp_path: Path, source: str):
    projects = _projects(monkeypatch, tmp_path)
    encoded = migrate.encode_path(source)
    _session(projects / encoded, "source-session", source)

    assert migrate.get_available_projects() == [(encoded, source)]


def test_available_projects_rejects_unresolved_source_path(monkeypatch, tmp_path: Path):
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / "-work-lossy-project"
    source_dir.mkdir()
    (source_dir / "source-session.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
    )

    with pytest.raises(migrate.ProjectPathResolutionError, match="actual path"):
        migrate.get_available_projects()


def test_available_projects_rejects_empty_unresolved_directory(monkeypatch, tmp_path: Path):
    projects = _projects(monkeypatch, tmp_path)
    (projects / migrate.encode_path("/work/empty")).mkdir()

    with pytest.raises(migrate.ProjectPathResolutionError, match="actual path"):
        migrate.get_available_projects()


def test_available_projects_rejects_ambiguous_source_path(monkeypatch, tmp_path: Path):
    projects = _projects(monkeypatch, tmp_path)
    encoded = migrate.encode_path("/work/my-project")
    _session(projects / encoded, "first", "/work/my-project")
    _session(projects / encoded, "second", "/work/my_project")

    with pytest.raises(migrate.ProjectPathResolutionError, match="Ambiguous actual path"):
        migrate.get_available_projects()


def test_partial_selection_cannot_replace_entire_target(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming-one", source)
    _session(source_dir, "incoming-two", source)
    _session(target_dir, "native", target)
    (target_dir / "memory").mkdir()
    (target_dir / "memory" / "native.txt").write_text("keep")
    (target_dir / "sessions-index.json").write_text("{}")

    result = migrate.migrate_sessions(
        source,
        target,
        mode="overwrite",
        session_ids=["incoming-one"],
    )

    assert not result.success
    assert "entire source project" in result.message
    assert (target_dir / "native.jsonl").exists()
    assert (target_dir / "memory" / "native.txt").read_text() == "keep"
    assert not (target_dir / "incoming-one.jsonl").exists()


def test_full_replace_moves_entire_target_and_copies_entire_source(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming-one", source)
    _session(source_dir, "incoming-two", source)
    (source_dir / "memory").mkdir()
    (source_dir / "memory" / "source.txt").write_text("source")
    _session(target_dir, "native", target)
    (target_dir / "memory").mkdir()
    (target_dir / "memory" / "native.txt").write_text("native")
    trashed = []

    def trash(path: str) -> None:
        target_path = Path(path)
        trashed.append(target_path)
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

    monkeypatch.setattr(migrate, "send2trash", trash)

    result = migrate.migrate_sessions(source, target, mode="overwrite")

    assert result.success
    assert result.sessions_copied == 2
    assert not (target_dir / "native.jsonl").exists()
    assert (target_dir / "incoming-one.jsonl").exists()
    assert (target_dir / "incoming-two.jsonl").exists()
    assert (target_dir / "memory" / "source.txt").read_text() == "source"
    assert not (target_dir / "memory" / "native.txt").exists()
    assert trashed
    assert (source_dir / "incoming-one.jsonl").exists()


def test_malformed_jsonl_rewrite_rolls_back_new_files(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source, "{broken-json\n")
    _session(target_dir, "native", target)

    result = migrate.migrate_sessions(source, target)

    assert not result.success
    assert "incoming.jsonl" in result.message
    assert (target_dir / "native.jsonl").exists()
    assert not (target_dir / "incoming.jsonl").exists()


def test_replace_rewrite_failure_preserves_existing_target(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source, "{broken-json\n")
    _session(target_dir, "native", target)
    (target_dir / "memory").mkdir()
    (target_dir / "memory" / "native.txt").write_text("keep")

    result = migrate.migrate_sessions(source, target, mode="overwrite")

    assert not result.success
    assert (target_dir / "native.jsonl").exists()
    assert (target_dir / "memory" / "native.txt").read_text() == "keep"
    assert not (target_dir / "incoming.jsonl").exists()


def test_malformed_index_rewrite_rolls_back_new_files(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    _session(target_dir, "native", target)
    (source_dir / "sessions-index.json").write_text("{broken-json")

    result = migrate.migrate_sessions(source, target)

    assert not result.success
    assert "sessions-index.json" in result.message
    assert (target_dir / "native.jsonl").exists()
    assert not (target_dir / "incoming.jsonl").exists()
    assert not (target_dir / "sessions-index.json").exists()


def test_jsonl_write_failure_does_not_leave_new_copy(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    _session(target_dir, "native", target)
    original_write_text = Path.write_text

    def fail_staged_write(path: Path, *args, **kwargs):
        if path.name == "incoming.jsonl" and path.parent.parent.name.startswith(".asm-migrate-"):
            raise OSError("write denied")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_staged_write)

    result = migrate.migrate_sessions(source, target)

    assert not result.success
    assert "incoming.jsonl" in result.message
    assert (target_dir / "native.jsonl").exists()
    assert not (target_dir / "incoming.jsonl").exists()


def test_replace_confirmation_lists_entire_target_scope(monkeypatch, tmp_path: Path):
    from asm.app import CCTuiApp
    from asm.models import encode_path
    from tests.test_feature_smoke import _setup_fake_claude

    env = _setup_fake_claude(monkeypatch, tmp_path)
    source = env["project_a"]
    target = str(Path(env["home"]) / "work" / "target-project")
    target_dir = Path(env["projects_dir"]) / encode_path(target)
    _session(target_dir, "native", target)
    (target_dir / "memory").mkdir()
    (target_dir / "memory" / "native.txt").write_text("keep")
    (target_dir / "sessions-index.json").write_text("{}")
    (target_dir / "other.bin").write_bytes(b"other")

    async def run():
        app = CCTuiApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            pane = app.query_one("MigratePane")
            pane._source_hint = source
            pane._source_encoded = env["encoded_a"]
            pane._target_hint = target
            pane._target_encoded = encode_path(target)
            pane._populate_session_table(source, [
                (env["session_id"], "07/24 10:00", "alpha", "1KB"),
            ])
            pane.action_toggle_all()
            pane._mode = "overwrite"
            pane._start_migrate()
            await pilot.pause()
            message = app.screen.message
            assert "Replace entire target" in message
            assert "1 session" in message
            assert "1 memory file" in message
            assert "sessions-index.json" in message
            assert "1 other entry" in message

    run_async_test(run())


def test_replace_ui_rejects_partial_source_selection(monkeypatch, tmp_path: Path):
    from asm.app import CCTuiApp
    from asm.models import encode_path
    from tests.test_feature_smoke import _setup_fake_claude

    env = _setup_fake_claude(monkeypatch, tmp_path)
    target = str(Path(env["home"]) / "work" / "target-project")

    async def run():
        app = CCTuiApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            pane = app.query_one("MigratePane")
            pane._source_hint = env["project_a"]
            pane._source_encoded = env["encoded_a"]
            pane._target_hint = target
            pane._target_encoded = encode_path(target)
            pane._populate_session_table(env["project_a"], [
                (env["session_id"], "07/24 10:00", "alpha", "1KB"),
                ("second", "07/24 11:00", "beta", "1KB"),
            ])
            pane.action_toggle_session()
            pane._mode = "overwrite"
            pane._start_migrate()
            await pilot.pause()
            assert len(app.screen_stack) == 1

    run_async_test(run())


@pytest.mark.parametrize("mode", ["append", "overwrite"])
def test_migration_rejects_target_directory_symlink(monkeypatch, tmp_path: Path, mode: str):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    outside = tmp_path / "outside"
    _session(source_dir, "incoming", source)
    _session(outside, "victim", target)
    target_dir.symlink_to(outside, target_is_directory=True)
    before = _snapshot(outside)

    result = migrate.migrate_sessions(
        source,
        target,
        mode=mode,
        session_ids=["incoming"] if mode == "append" else None,
    )

    assert not result.success
    assert "symlink" in result.message
    assert _snapshot(outside) == before


def test_migration_rejects_lossy_target_collision(monkeypatch, tmp_path: Path):
    source = "/work/source"
    recorded_target = "/work/my-project"
    requested_target = "/work/my_project"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(recorded_target)
    _session(source_dir, "incoming", source)
    _session(target_dir, "native", recorded_target)
    before = _snapshot(target_dir)

    result = migrate.migrate_sessions(
        source,
        requested_target,
        session_ids=["incoming"],
    )

    assert not result.success
    assert "Target path mismatch" in result.message
    assert _snapshot(target_dir) == before


def test_migration_rejects_unresolved_existing_target(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    target_dir.mkdir()

    result = migrate.migrate_sessions(source, target, session_ids=["incoming"])

    assert not result.success
    assert "resolve actual target path" in result.message
    assert _snapshot(target_dir) == {}


def test_migration_rejects_target_encoded_mismatch(monkeypatch, tmp_path: Path):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    _session(source_dir, "incoming", source)

    result = migrate.migrate_sessions(
        source,
        target,
        target_encoded="not-the-target",
        session_ids=["incoming"],
    )

    assert not result.success
    assert "encoded directory" in result.message
    assert not (projects / "not-the-target").exists()


@pytest.mark.parametrize("session_ids", [[], ["missing"], ["incoming", "missing"]])
def test_migration_rejects_empty_or_missing_session_selection(
    monkeypatch, tmp_path: Path, session_ids: list[str]
):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    _session(source_dir, "incoming", source)

    result = migrate.migrate_sessions(source, target, session_ids=session_ids)

    assert not result.success
    assert "session" in result.message.lower()
    assert not (projects / migrate.encode_path(target)).exists()


@pytest.mark.parametrize("mode", ["append", "overwrite"])
def test_migration_stage_failure_preserves_target(monkeypatch, tmp_path: Path, mode: str):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    (source_dir / "memory").mkdir()
    (source_dir / "memory" / "new.txt").write_text("new")
    _session(target_dir, "native", target)
    (target_dir / "memory").mkdir()
    (target_dir / "memory" / "native.txt").write_text("native")
    before = _snapshot(target_dir)
    original_copy2 = migrate.shutil.copy2

    def fail_new_memory(source_file, destination, *args, **kwargs):
        if Path(source_file).name == "new.txt":
            raise OSError("memory copy failed")
        return original_copy2(source_file, destination, *args, **kwargs)

    monkeypatch.setattr(migrate.shutil, "copy2", fail_new_memory)

    result = migrate.migrate_sessions(
        source,
        target,
        mode=mode,
        session_ids=["incoming"] if mode == "append" else None,
    )

    assert not result.success
    assert _snapshot(target_dir) == before


@pytest.mark.parametrize("mode", ["append", "overwrite"])
def test_migration_swap_failure_rolls_back_target(monkeypatch, tmp_path: Path, mode: str):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    _session(target_dir, "native", target)
    before = _snapshot(target_dir)
    original_replace = migrate.os.replace
    calls = 0

    def fail_install(source_path, target_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("install failed")
        return original_replace(source_path, target_path)

    monkeypatch.setattr(migrate.os, "replace", fail_install)

    result = migrate.migrate_sessions(
        source,
        target,
        mode=mode,
        session_ids=["incoming"] if mode == "append" else None,
    )

    assert not result.success
    assert "install failed" in result.message
    assert _snapshot(target_dir) == before


@pytest.mark.parametrize("mode", ["append", "overwrite"])
def test_migration_install_failure_restores_absent_target(monkeypatch, tmp_path: Path, mode: str):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)

    def fail_install(_source_path, _target_path):
        raise OSError("install failed")

    monkeypatch.setattr(migrate.os, "replace", fail_install)

    result = migrate.migrate_sessions(
        source,
        target,
        mode=mode,
        session_ids=["incoming"] if mode == "append" else None,
    )

    assert not result.success
    assert "install failed" in result.message
    assert not target_dir.exists()


@pytest.mark.parametrize("mode", ["append", "overwrite"])
def test_migration_trash_failure_rolls_back_target(monkeypatch, tmp_path: Path, mode: str):
    source = "/work/source"
    target = "/work/target"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    target_dir = projects / migrate.encode_path(target)
    _session(source_dir, "incoming", source)
    _session(target_dir, "native", target)
    before = _snapshot(target_dir)

    def fail_trash(_path: str) -> None:
        raise OSError("trash failed")

    monkeypatch.setattr(migrate, "send2trash", fail_trash)

    result = migrate.migrate_sessions(
        source,
        target,
        mode=mode,
        session_ids=["incoming"] if mode == "append" else None,
    )

    assert not result.success
    assert "trash failed" in result.message
    assert _snapshot(target_dir) == before


def test_migration_rewrites_only_path_boundaries_and_schema_fields(monkeypatch, tmp_path: Path):
    source = "/work/app"
    target = "/srv/new"
    projects = _projects(monkeypatch, tmp_path)
    source_dir = projects / migrate.encode_path(source)
    source_dir.mkdir()
    session = source_dir / "incoming.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "cwd": source, "message": {"content": source}}),
                json.dumps({"type": "assistant", "cwd": f"{source}/sub"}),
                json.dumps({"type": "assistant", "cwd": "/work/application"}),
                json.dumps({"type": "user", "message": {"cwd": source, "path": source}}),
            ]
        )
        + "\n"
    )
    source_index_path = str(source_dir / "incoming.jsonl")
    (source_dir / "sessions-index.json").write_text(
        json.dumps(
            {
                "projectPath": source,
                "entries": [
                    {
                        "projectPath": f"{source}/sub",
                        "fullPath": source_index_path,
                        "summary": f"Keep {source} in user text",
                        "metadata": {"path": source},
                    }
                ],
            }
        )
    )

    result = migrate.migrate_sessions(source, target, session_ids=["incoming"])

    assert result.success
    target_dir = projects / migrate.encode_path(target)
    rows = [json.loads(line) for line in (target_dir / "incoming.jsonl").read_text().splitlines()]
    assert rows[0]["cwd"] == target
    assert rows[0]["message"]["content"] == source
    assert rows[1]["cwd"] == f"{target}/sub"
    assert rows[2]["cwd"] == "/work/application"
    assert rows[3]["message"] == {"cwd": source, "path": source}
    index = json.loads((target_dir / "sessions-index.json").read_text())
    assert index["projectPath"] == target
    assert index["entries"][0]["projectPath"] == f"{target}/sub"
    assert migrate.encode_path(target) in index["entries"][0]["fullPath"]
    assert index["entries"][0]["summary"] == f"Keep {source} in user text"
    assert index["entries"][0]["metadata"]["path"] == source
