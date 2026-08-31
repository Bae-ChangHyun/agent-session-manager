from __future__ import annotations

import json
import os
import shutil
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from asm.services import backup, recovery


def _write_archive(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, BytesIO(payload))


def _patch_backup_paths(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    claude_json = tmp_path / ".claude.json"
    backup_dir = tmp_path / ".asm" / "backups"
    projects = claude_dir / "projects"
    plugins = claude_dir / "plugins"
    skills = claude_dir / "skills"
    codex_dir = tmp_path / ".codex"
    codex_sessions = codex_dir / "sessions"
    monkeypatch.setattr(backup, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(backup, "CLAUDE_JSON", claude_json)
    monkeypatch.setattr(backup, "BACKUP_BASE_DIR", backup_dir)
    monkeypatch.setattr(backup, "PROJECTS_DIR", projects)
    monkeypatch.setattr(backup, "PLUGINS_DIR", plugins)
    monkeypatch.setattr(backup, "SKILLS_DIR", skills)
    monkeypatch.setattr(backup, "CODEX_DIR", codex_dir)
    monkeypatch.setattr(backup, "CODEX_SESSIONS_DIR", codex_sessions)
    monkeypatch.setattr(
        backup,
        "SETTINGS_FILES",
        [claude_dir / "settings.json", claude_dir / "settings.local.json"],
    )
    return {
        "claude_dir": claude_dir,
        "claude_json": claude_json,
        "backup_dir": backup_dir,
        "projects": projects,
        "plugins": plugins,
        "skills": skills,
        "codex_dir": codex_dir,
        "codex_sessions": codex_sessions,
    }


def _patch_recovery_paths(monkeypatch, tmp_path: Path, claude_dir: Path) -> Path:
    from asm.services import codex_data

    recovery_dir = tmp_path / ".asm" / "recovery"
    monkeypatch.setattr(recovery, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(recovery, "RECOVERY_BASE_DIR", recovery_dir)
    monkeypatch.setattr(
        codex_data, "CODEX_SESSIONS_DIR", tmp_path / "no-codex" / "sessions"
    )
    return recovery_dir


def _fail_second_staged_replace(destinations: set[Path]):
    real_replace = os.replace
    calls = 0

    def replace(src, dst):
        nonlocal calls
        src_path = Path(src)
        dst_path = Path(dst)
        if dst_path in destinations and ".asm-stage-" in src_path.name:
            calls += 1
            if calls == 2:
                raise OSError("injected replace failure")
        return real_replace(src, dst)

    return replace


def test_config_backup_fails_and_removes_artifact_when_chmod_fails(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["claude_json"].write_text('{"token":"secret"}')
    real_chmod = Path.chmod

    def chmod(path: Path, mode: int, *args, **kwargs):
        if path.is_file() and path.parent.name == "config":
            raise PermissionError("chmod denied")
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)

    assert backup.create_config_backup() is None
    assert not list((paths["backup_dir"] / "config").glob("*.json"))


def test_sessions_backup_fails_before_copy_when_chmod_fails(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["projects"].mkdir()
    (paths["projects"] / "session.jsonl").write_text("secret")
    real_chmod = Path.chmod

    def chmod(path: Path, mode: int, *args, **kwargs):
        if path.name.startswith("sessions-"):
            raise PermissionError("chmod denied")
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)

    assert backup.create_sessions_backup() is None
    assert not list(paths["backup_dir"].glob("sessions-*"))


def test_recovery_snapshot_fails_when_owner_only_chmod_fails(
    monkeypatch, tmp_path: Path
):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    target = claude_dir / "session.jsonl"
    target.write_text("secret")
    recovery_dir = _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    real_chmod = Path.chmod

    def chmod(path: Path, mode: int, *args, **kwargs):
        if path == recovery_dir:
            raise PermissionError("chmod denied")
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)

    assert recovery.create_recovery_snapshot(target, "session") is None
    assert not recovery_dir.exists() or not any(recovery_dir.iterdir())


def test_restore_config_aborts_when_safety_backup_fails(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["claude_json"].write_text("old")
    source = paths["backup_dir"] / "config" / ".claude-source.json"
    source.parent.mkdir(parents=True)
    source.write_text("new")
    monkeypatch.setattr(backup, "create_config_backup", lambda: None)

    assert backup.restore_config_backup(str(source)) is False
    assert paths["claude_json"].read_text() == "old"


def test_restore_settings_aborts_when_safety_backup_fails(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    live = paths["claude_dir"] / "settings.json"
    live.write_text("old")
    source = paths["backup_dir"] / "settings-source"
    source.mkdir(parents=True)
    (source / "settings.json").write_text("new")
    monkeypatch.setattr(backup, "create_settings_backup", lambda: None)

    assert backup.restore_settings_backup(str(source)) is False
    assert live.read_text() == "old"


def test_config_export_import_list_restore_roundtrip(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["claude_json"].write_text('{"value":"original"}')
    created = backup.create_config_backup()
    assert created
    archive = backup.export_backup(created, str(tmp_path / "exports"))
    assert archive
    Path(created).unlink()

    imported = backup.import_backup(archive)
    assert imported and Path(imported).parent == paths["backup_dir"] / "config"
    assert any(item.path == imported for item in backup.list_backups())
    paths["claude_json"].write_text('{"value":"damaged"}')
    assert backup.restore_config_backup(imported) is True
    assert json.loads(paths["claude_json"].read_text()) == {"value": "original"}


@pytest.mark.skipif(os.name == "nt", reason="Symlink behavior differs on Windows")
def test_symlink_backup_export_import_list_restore_roundtrip(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["plugins"].mkdir()
    target = paths["plugins"] / "shared-skill"
    target.mkdir()
    (target / "SKILL.md").write_text("skill")
    (paths["plugins"] / "shared").symlink_to("shared-skill", target_is_directory=True)
    created = backup.create_plugins_backup()
    assert created
    archive = backup.export_backup(created, str(tmp_path / "exports"))
    assert archive
    shutil.rmtree(created)

    imported = backup.import_backup(archive)
    assert imported
    imported_link = Path(imported) / "plugins" / "shared"
    assert imported_link.is_symlink()
    assert any(item.path == imported for item in backup.list_backups())
    (paths["plugins"] / "shared").unlink()
    assert backup.restore_plugins_backup(imported)[0] is True
    assert (paths["plugins"] / "shared").is_symlink()
    assert (paths["plugins"] / "shared").resolve() == paths["plugins"] / "shared-skill"


def test_backup_selector_rejects_base_and_aliases(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    artifact = paths["backup_dir"] / "settings-direct"
    artifact.mkdir(parents=True)
    alias = paths["backup_dir"] / "settings-alias"
    alias.symlink_to(artifact, target_is_directory=True)
    traversal_alias = artifact / ".." / artifact.name

    for selector in (paths["backup_dir"], alias, traversal_alias):
        with pytest.raises(ValueError):
            backup._validate_backup_path(selector)

    assert backup.delete_backup(str(paths["backup_dir"])) is False
    assert backup.delete_backup(str(alias)) is False
    assert artifact.exists()


def test_import_rejects_relative_symlink_escaping_archive(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    archive = tmp_path / "external-relative-symlink.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        root = tarfile.TarInfo("plugins-a")
        root.type = tarfile.DIRTYPE
        tar.addfile(root)
        link = tarfile.TarInfo("plugins-a/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        tar.addfile(link)

    assert backup.import_backup(str(archive)) is None
    assert not (tmp_path / "outside").exists()
    assert not any(paths["backup_dir"].glob("plugins-a"))


def test_import_rejects_existing_top_level_name(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    existing = paths["backup_dir"] / "settings-collision"
    existing.mkdir(parents=True)
    (existing / "settings.json").write_text("old")
    archive = tmp_path / "collision.tar.gz"
    _write_archive(archive, [("settings-collision/settings.json", b"new")])

    assert backup.import_backup(str(archive)) is None
    assert (existing / "settings.json").read_text() == "old"


def test_import_rejects_member_beneath_symlink(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    archive = tmp_path / "symlink-parent.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("settings-a/link")
        link.type = tarfile.SYMTYPE
        link.linkname = str(tmp_path / "outside")
        tar.addfile(link)
        payload = b"escape"
        child = tarfile.TarInfo("settings-a/link/child")
        child.size = len(payload)
        tar.addfile(child, BytesIO(payload))

    assert backup.import_backup(str(archive)) is None
    assert not (tmp_path / "outside" / "child").exists()
    assert not any(paths["backup_dir"].glob("settings-a"))


@pytest.mark.parametrize(
    ("limit_name", "limit", "members"),
    [
        ("_MAX_ARCHIVE_MEMBERS", 1, [("settings-a/a", b"1"), ("settings-a/b", b"2")]),
        ("_MAX_ARCHIVE_MEMBER_BYTES", 3, [("settings-a/a", b"1234")]),
        ("_MAX_ARCHIVE_TOTAL_BYTES", 3, [("settings-a/a", b"12"), ("settings-a/b", b"12")]),
        ("_MAX_ARCHIVE_COMPRESSION_RATIO", 0.01, [("settings-a/a", b"1234")]),
    ],
)
def test_import_rejects_archive_limits(
    monkeypatch,
    tmp_path: Path,
    limit_name: str,
    limit: int | float,
    members: list[tuple[str, bytes]],
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    archive = tmp_path / "limited.tar.gz"
    _write_archive(archive, members)
    monkeypatch.setattr(backup, limit_name, limit)

    assert backup.import_backup(str(archive)) is None
    assert not any(paths["backup_dir"].glob("settings-a"))


def test_self_export_respects_import_member_cap(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    source = paths["backup_dir"] / "settings-cap"
    source.mkdir(parents=True)
    (source / "settings.json").write_text("{}")
    monkeypatch.setattr(backup, "_MAX_ARCHIVE_MEMBERS", 2)

    archive = backup.export_backup(str(source), str(tmp_path / "exports"))
    assert archive
    shutil.rmtree(source)
    assert backup.import_backup(archive) is not None


def test_self_export_rejects_archive_over_member_cap(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    source = paths["backup_dir"] / "settings-cap"
    source.mkdir(parents=True)
    (source / "settings.json").write_text("{}")
    monkeypatch.setattr(backup, "_MAX_ARCHIVE_MEMBERS", 1)

    assert backup.export_backup(str(source), str(tmp_path / "exports")) is None
    assert not list((tmp_path / "exports").glob("*.tar.gz"))


def test_import_preserves_modes_and_secures_sensitive_files(monkeypatch, tmp_path: Path):
    _patch_backup_paths(monkeypatch, tmp_path)
    archive = tmp_path / "modes.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        root = tarfile.TarInfo("settings-modes")
        root.type = tarfile.DIRTYPE
        root.mode = 0o750
        tar.addfile(root)
        script_data = b"#!/bin/sh\n"
        script = tarfile.TarInfo("settings-modes/tool.sh")
        script.mode = 0o751
        script.size = len(script_data)
        tar.addfile(script, BytesIO(script_data))
        settings_data = b"{}"
        settings = tarfile.TarInfo("settings-modes/settings.json")
        settings.mode = 0o444
        settings.size = len(settings_data)
        tar.addfile(settings, BytesIO(settings_data))

    imported = backup.import_backup(str(archive))
    assert imported
    assert (Path(imported) / "tool.sh").stat().st_mode & 0o777 == 0o751
    assert (Path(imported) / "settings.json").stat().st_mode & 0o777 == 0o600


def test_full_restore_rolls_back_all_targets_on_second_replace_failure(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    (paths["claude_dir"] / "state.txt").write_text("old-dir")
    paths["claude_json"].write_text("old-json")
    source = paths["backup_dir"] / "full-source"
    (source / ".claude").mkdir(parents=True)
    (source / ".claude" / "state.txt").write_text("new-dir")
    (source / ".claude.json").write_text("new-json")
    monkeypatch.setattr(
        backup.os,
        "replace",
        _fail_second_staged_replace({paths["claude_dir"], paths["claude_json"]}),
    )

    assert backup.restore_full_backup(str(source)) is False
    assert (paths["claude_dir"] / "state.txt").read_text() == "old-dir"
    assert paths["claude_json"].read_text() == "old-json"


def test_settings_restore_rolls_back_all_files_on_second_replace_failure(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    one = paths["claude_dir"] / "settings.json"
    two = paths["claude_dir"] / "settings.local.json"
    one.write_text("old-one")
    two.write_text("old-two")
    source = paths["backup_dir"] / "settings-source"
    source.mkdir(parents=True)
    (source / one.name).write_text("new-one")
    (source / two.name).write_text("new-two")
    monkeypatch.setattr(
        backup.os, "replace", _fail_second_staged_replace({one, two})
    )

    assert backup.restore_settings_backup(str(source)) is False
    assert one.read_text() == "old-one"
    assert two.read_text() == "old-two"


def test_plugins_restore_rolls_back_both_trees_on_second_replace_failure(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["plugins"].mkdir()
    paths["skills"].mkdir()
    (paths["plugins"] / "state.txt").write_text("old-plugins")
    (paths["skills"] / "state.txt").write_text("old-skills")
    source = paths["backup_dir"] / "plugins-source"
    (source / "plugins").mkdir(parents=True)
    (source / "skills").mkdir()
    (source / "plugins" / "state.txt").write_text("new-plugins")
    (source / "skills" / "state.txt").write_text("new-skills")
    monkeypatch.setattr(
        backup.os,
        "replace",
        _fail_second_staged_replace({paths["plugins"], paths["skills"]}),
    )

    assert backup.restore_plugins_backup(str(source))[0] is False
    assert (paths["plugins"] / "state.txt").read_text() == "old-plugins"
    assert (paths["skills"] / "state.txt").read_text() == "old-skills"


def test_codex_restore_rolls_back_sessions_and_files_on_second_replace_failure(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["codex_sessions"].mkdir(parents=True)
    (paths["codex_sessions"] / "state.txt").write_text("old-sessions")
    live_config = paths["codex_dir"] / "config.toml"
    live_config.write_text("old-config")
    source = paths["backup_dir"] / "codex-source"
    (source / "sessions").mkdir(parents=True)
    (source / "sessions" / "state.txt").write_text("new-sessions")
    (source / "config.toml").write_text("new-config")
    monkeypatch.setattr(
        backup.os,
        "replace",
        _fail_second_staged_replace({paths["codex_sessions"], live_config}),
    )

    assert backup.restore_codex_backup(str(source)) is False
    assert (paths["codex_sessions"] / "state.txt").read_text() == "old-sessions"
    assert live_config.read_text() == "old-config"


def test_codex_restore_accepts_config_only_backup(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    live_config = paths["codex_dir"] / "config.toml"
    live_config.parent.mkdir()
    live_config.write_text("old-config")
    source = paths["backup_dir"] / "codex-config-only"
    source.mkdir(parents=True)
    (source / "config.toml").write_text("new-config")

    assert backup.restore_codex_backup(str(source)) is True
    assert live_config.read_text() == "new-config"
    safety_backups = [
        item for item in backup.list_backups() if item.backup_type == "codex"
    ]
    assert len(safety_backups) == 2


def test_plugins_restore_reports_post_diagnostic_failure(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    source = paths["backup_dir"] / "plugins-source"
    (source / "plugins").mkdir(parents=True)
    (source / "plugins" / "installed.json").write_text("{}")

    def fail_diagnostic(path: Path):
        raise PermissionError(f"cannot scan {path}")

    monkeypatch.setattr(backup, "detect_broken_symlinks", fail_diagnostic)

    result = backup.restore_plugins_backup(str(source))
    assert result.success is True
    assert result.warnings[0].code == "post_restore_diagnostic_failed"
    assert result.warnings[0].path == str(paths["plugins"])


def test_oversized_recovery_snapshot_is_removed(monkeypatch, tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    target = claude_dir / "large.jsonl"
    target.write_bytes(b"12345")
    recovery_dir = _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    monkeypatch.setattr(recovery, "_MAX_ITEM_BYTES", 4)

    assert recovery.create_recovery_snapshot(target, "session") is None
    assert not recovery_dir.exists() or not any(recovery_dir.iterdir())


def test_recovery_batch_prunes_old_item_but_keeps_current_batch(monkeypatch, tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    recovery_dir = _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    targets = [claude_dir / name for name in ("old", "main", "related")]
    for target in targets:
        target.write_text(target.name)
    monkeypatch.setattr(recovery, "_MAX_ITEMS", 2)

    old_id = recovery.create_recovery_snapshot(targets[0], "old")
    batch_ids = recovery.create_recovery_snapshots(
        [(targets[1], "session"), (targets[2], "session-env")]
    )

    assert old_id
    assert batch_ids and len(batch_ids) == 2
    assert {item.id for item in recovery.list_recovery_items()} == set(batch_ids)
    assert not (recovery_dir / old_id).exists()


def test_recovery_batch_over_cap_fails_without_pruning_existing(monkeypatch, tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    recovery_dir = _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    targets = [claude_dir / name for name in ("old", "main", "related")]
    for target in targets:
        target.write_text(target.name)
    monkeypatch.setattr(recovery, "_MAX_ITEMS", 1)

    old_id = recovery.create_recovery_snapshot(targets[0], "old")
    batch_ids = recovery.create_recovery_snapshots(
        [(targets[1], "session"), (targets[2], "session-env")]
    )

    assert old_id
    assert batch_ids is None
    assert (recovery_dir / old_id).exists()
    assert {item.id for item in recovery.list_recovery_items()} == {old_id}


def test_overwrite_recovery_copy_failure_preserves_original(
    monkeypatch, tmp_path: Path
):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    target = claude_dir / "session.jsonl"
    target.write_text("snapshot")
    _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    item_id = recovery.create_recovery_snapshot(target, "session")
    assert item_id
    target.write_text("live")
    trash_calls: list[str] = []
    monkeypatch.setattr(recovery, "send2trash", trash_calls.append)

    def fail_copy(*args, **kwargs):
        raise OSError("injected copy failure")

    monkeypatch.setattr(recovery.shutil, "copy2", fail_copy)

    ok, _ = recovery.restore_recovery_item(item_id, overwrite=True)
    assert ok is False
    assert target.read_text() == "live"
    assert trash_calls == []


def test_overwrite_recovery_trash_failure_rolls_back_original(
    monkeypatch, tmp_path: Path
):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    target = claude_dir / "session.jsonl"
    target.write_text("snapshot")
    _patch_recovery_paths(monkeypatch, tmp_path, claude_dir)
    item_id = recovery.create_recovery_snapshot(target, "session")
    assert item_id
    target.write_text("live")

    def fail_trash(path: str):
        raise OSError("injected trash failure")

    monkeypatch.setattr(recovery, "send2trash", fail_trash)

    ok, _ = recovery.restore_recovery_item(item_id, overwrite=True)
    assert ok is False
    assert target.read_text() == "live"
    assert not list(claude_dir.glob(".*.asm-*"))


def test_full_backup_without_source_returns_none_and_creates_nothing(
    monkeypatch, tmp_path: Path
):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    paths["claude_dir"].rmdir()

    assert backup.create_full_backup() is None
    assert not paths["backup_dir"].exists() or not list(paths["backup_dir"].glob("full-*"))


def test_failed_full_backup_removes_partial_artifact(monkeypatch, tmp_path: Path):
    paths = _patch_backup_paths(monkeypatch, tmp_path)
    (paths["claude_dir"] / "state.txt").write_text("state")
    paths["claude_json"].write_text("config")

    def fail_copy(*args, **kwargs):
        raise OSError("injected copy failure")

    monkeypatch.setattr(backup.shutil, "copy2", fail_copy)

    assert backup.create_full_backup() is None
    assert not list(paths["backup_dir"].glob("full-*"))
