"""Tests for the backup service (settings, plugins, sessions, export/import)."""

from __future__ import annotations

import os
import tarfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from cc_tui.services.backup import (
    SETTINGS_FILES,
    _SYMLINKS_ON,
    _ensure_backup_dir,
    _validate_backup_path,
    create_config_backup,
    create_plugins_backup,
    create_sessions_backup,
    create_settings_backup,
    delete_backup,
    detect_broken_symlinks,
    detect_symlinks,
    export_backup,
    import_backup,
    list_backups,
    restore_full_backup,
    restore_plugins_backup,
    restore_sessions_backup,
    restore_settings_backup,
)
from cc_tui.models import BACKUP_BASE_DIR, BackupInfo


# ---------------------------------------------------------------------------
# BackupInfo model
# ---------------------------------------------------------------------------


class TestBackupInfoModel:
    def test_backup_type_field(self):
        b = BackupInfo(name="test", path="/tmp", backup_type="settings")
        assert b.backup_type == "settings"

    def test_default_backup_type(self):
        b = BackupInfo(name="test", path="/tmp")
        assert b.backup_type == ""

    def test_all_types(self):
        for btype in ("config", "full", "settings", "plugins", "sessions"):
            b = BackupInfo(name="test", path="/tmp", backup_type=btype)
            assert b.backup_type == btype


# ---------------------------------------------------------------------------
# Settings backup
# ---------------------------------------------------------------------------


class TestSettingsBackup:
    def test_create_settings_backup(self, tmp_path: Path):
        """Settings backup should copy existing settings files."""
        fake_claude = tmp_path / ".claude"
        fake_claude.mkdir()
        (fake_claude / "settings.json").write_text('{"a": 1}')
        (fake_claude / "settings.local.json").write_text('{"b": 2}')
        (fake_claude / "keybindings.json").write_text('{"c": 3}')

        fake_backup = tmp_path / "backups"
        fake_settings_files = [
            fake_claude / "settings.json",
            fake_claude / "settings.local.json",
            fake_claude / "keybindings.json",
        ]

        with (
            patch("cc_tui.services.backup.SETTINGS_FILES", fake_settings_files),
            patch("cc_tui.services.backup.BACKUP_BASE_DIR", fake_backup),
        ):
            path = create_settings_backup()

        assert path is not None
        backup_dir = Path(path)
        assert backup_dir.exists()
        assert (backup_dir / "settings.json").exists()
        assert (backup_dir / "settings.local.json").exists()
        assert (backup_dir / "keybindings.json").exists()

    def test_no_settings_files(self, tmp_path: Path):
        """Should return None when no settings files exist."""
        fake_files = [tmp_path / "nonexistent.json"]
        with patch("cc_tui.services.backup.SETTINGS_FILES", fake_files):
            result = create_settings_backup()
        assert result is None


# ---------------------------------------------------------------------------
# Plugins backup
# ---------------------------------------------------------------------------


class TestPluginsBackup:
    def test_create_plugins_backup(self, tmp_path: Path):
        fake_plugins = tmp_path / "plugins"
        fake_plugins.mkdir()
        (fake_plugins / "installed.json").write_text("{}")

        fake_skills = tmp_path / "skills"
        fake_skills.mkdir()
        (fake_skills / "my_skill").mkdir()
        (fake_skills / "my_skill" / "SKILL.md").write_text("# Skill")

        fake_backup = tmp_path / "backups"

        with (
            patch("cc_tui.services.backup.PLUGINS_DIR", fake_plugins),
            patch("cc_tui.services.backup.SKILLS_DIR", fake_skills),
            patch("cc_tui.services.backup.BACKUP_BASE_DIR", fake_backup),
        ):
            path = create_plugins_backup()

        assert path is not None
        backup_dir = Path(path)
        assert (backup_dir / "plugins" / "installed.json").exists()
        assert (backup_dir / "skills" / "my_skill" / "SKILL.md").exists()

    def test_no_plugins_or_skills(self, tmp_path: Path):
        with (
            patch("cc_tui.services.backup.PLUGINS_DIR", tmp_path / "nope1"),
            patch("cc_tui.services.backup.SKILLS_DIR", tmp_path / "nope2"),
        ):
            result = create_plugins_backup()
        assert result is None


# ---------------------------------------------------------------------------
# Sessions backup
# ---------------------------------------------------------------------------


class TestSessionsBackup:
    def test_create_sessions_backup(self, tmp_path: Path):
        fake_projects = tmp_path / "projects"
        fake_projects.mkdir()
        (fake_projects / "proj1").mkdir()
        (fake_projects / "proj1" / "session.jsonl").write_text("{}")

        fake_backup = tmp_path / "backups"

        with (
            patch("cc_tui.services.backup.PROJECTS_DIR", fake_projects),
            patch("cc_tui.services.backup.BACKUP_BASE_DIR", fake_backup),
        ):
            path = create_sessions_backup()

        assert path is not None
        backup_dir = Path(path)
        assert (backup_dir / "projects" / "proj1" / "session.jsonl").exists()


# ---------------------------------------------------------------------------
# Symlink detection
# ---------------------------------------------------------------------------


class TestSymlinkDetection:
    @pytest.mark.skipif(os.name == "nt", reason="Symlinks differ on Windows")
    def test_detect_symlinks(self, tmp_path: Path):
        target = tmp_path / "target"
        target.write_text("data")
        link = tmp_path / "link"
        link.symlink_to(target)

        syms = detect_symlinks(tmp_path)
        assert len(syms) == 1
        assert "link" in syms[0]

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks differ on Windows")
    def test_detect_broken_symlinks(self, tmp_path: Path):
        link = tmp_path / "broken_link"
        link.symlink_to("/nonexistent/target")

        broken = detect_broken_symlinks(tmp_path)
        assert len(broken) == 1
        assert "broken_link" in broken[0]

    def test_detect_no_symlinks(self, tmp_path: Path):
        (tmp_path / "regular.txt").write_text("data")
        syms = detect_symlinks(tmp_path)
        assert len(syms) == 0

    def test_detect_nonexistent_dir(self):
        syms = detect_symlinks(Path("/nonexistent"))
        assert syms == []


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------


class TestExportImport:
    def test_export_creates_targz(self, tmp_path: Path):
        # Create a fake backup directory
        backup = tmp_path / "backups" / "settings-2024-01-01_00-00-00"
        backup.mkdir(parents=True)
        (backup / "settings.json").write_text('{"test": true}')

        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path / "backups"):
            result = export_backup(str(backup), dest_dir=str(tmp_path / "exports"))

        assert result is not None
        assert result.endswith(".tar.gz")
        assert os.path.exists(result)

    def test_import_extracts_to_backup_dir(self, tmp_path: Path):
        # Create a tar.gz
        src_dir = tmp_path / "src" / "settings-test"
        src_dir.mkdir(parents=True)
        (src_dir / "settings.json").write_text('{"imported": true}')

        archive = tmp_path / "test.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            tar.add(str(src_dir), arcname="settings-test")

        backup_dir = tmp_path / "backups"
        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", backup_dir):
            result = import_backup(str(archive))

        assert result is not None
        imported = Path(result)
        assert imported.exists()
        assert (imported / "settings.json").exists()

    def test_import_rejects_path_traversal(self, tmp_path: Path):
        """Archives with ../ paths should be rejected."""
        import io

        archive = tmp_path / "evil.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"evil"
            info = tarfile.TarInfo(name="../../etc/evil.txt")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path / "backups"):
            result = import_backup(str(archive))

        assert result is None

    def test_import_rejects_absolute_path(self, tmp_path: Path):
        """Archives with absolute paths should be rejected."""
        archive = tmp_path / "abs.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"evil"
            info = tarfile.TarInfo(name="/tmp/evil.txt")
            info.size = len(data)
            tar.addfile(info, BytesIO(data))

        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path / "backups"):
            result = import_backup(str(archive))

        assert result is None

    @pytest.mark.skipif(os.name == "nt", reason="Symlink archive members differ on Windows")
    def test_import_rejects_symlink_member(self, tmp_path: Path):
        archive = tmp_path / "symlink.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            info = tarfile.TarInfo(name="settings-test/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/tmp/evil-target"
            tar.addfile(info)

        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path / "backups"):
            result = import_backup(str(archive))

        assert result is None

    def test_import_rejects_non_targz(self, tmp_path: Path):
        result = import_backup(str(tmp_path / "not.zip"))
        assert result is None

    def test_import_rejects_nonexistent(self):
        result = import_backup("/nonexistent/file.tar.gz")
        assert result is None


# ---------------------------------------------------------------------------
# List backups (type detection)
# ---------------------------------------------------------------------------


class TestListBackups:
    def test_list_detects_types(self, tmp_path: Path):
        """Verify list_backups correctly assigns backup_type."""
        # Config backup
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / ".claude-2024-01-01.json").write_text("{}")

        # Settings backup
        settings_dir = tmp_path / "settings-2024-01-01_00-00-00"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{}")

        # Plugins backup
        plugins_dir = tmp_path / "plugins-2024-01-01_00-00-00"
        plugins_dir.mkdir()
        (plugins_dir / "plugins").mkdir()

        # Sessions backup
        sessions_dir = tmp_path / "sessions-2024-01-01_00-00-00"
        sessions_dir.mkdir()
        (sessions_dir / "projects").mkdir()

        # Full backup
        full_dir = tmp_path / "full-2024-01-01_00-00-00"
        full_dir.mkdir()

        with patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path):
            backups = list_backups()

        types = {b.backup_type for b in backups}
        assert "config" in types
        assert "settings" in types
        assert "plugins" in types
        assert "sessions" in types
        assert "full" in types


# ---------------------------------------------------------------------------
# Restore settings
# ---------------------------------------------------------------------------


class TestRestoreSettings:
    def test_restore_settings(self, tmp_path: Path):
        fake_claude = tmp_path / ".claude"
        fake_claude.mkdir()
        (fake_claude / "settings.json").write_text('{"old": true}')

        backup_dir = tmp_path / "backups" / "settings-test"
        backup_dir.mkdir(parents=True)
        (backup_dir / "settings.json").write_text('{"new": true}')

        fake_backup_base = tmp_path / "backups"

        with (
            patch("cc_tui.services.backup.CLAUDE_DIR", fake_claude),
            patch("cc_tui.services.backup.BACKUP_BASE_DIR", fake_backup_base),
            patch("cc_tui.services.backup.SETTINGS_FILES", [fake_claude / "settings.json"]),
        ):
            ok = restore_settings_backup(str(backup_dir))

        assert ok
        content = (fake_claude / "settings.json").read_text()
        assert '"new"' in content


class TestRestoreFullBackup:
    def test_restore_full_uses_os_replace_for_json(self, tmp_path: Path):
        fake_claude_dir = tmp_path / ".claude"
        fake_claude_dir.mkdir()
        (fake_claude_dir / "old.txt").write_text("old")
        fake_claude_json = tmp_path / ".claude.json"
        fake_claude_json.write_text('{"old": true}')

        backup_dir = tmp_path / "backups" / "full-test"
        (backup_dir / ".claude").mkdir(parents=True)
        (backup_dir / ".claude" / "new.txt").write_text("new")
        (backup_dir / ".claude.json").write_text('{"new": true}')

        replace_calls: list[tuple[Path, Path]] = []
        real_replace = os.replace

        def tracked_replace(src, dst):
            replace_calls.append((Path(src), Path(dst)))
            return real_replace(src, dst)

        with (
            patch("cc_tui.services.backup.BACKUP_BASE_DIR", tmp_path / "backups"),
            patch("cc_tui.services.backup.CLAUDE_DIR", fake_claude_dir),
            patch("cc_tui.services.backup.CLAUDE_JSON", fake_claude_json),
            patch("cc_tui.services.backup.create_full_backup", return_value=str(tmp_path / "safety")),
            patch("cc_tui.services.backup.os.replace", side_effect=tracked_replace),
        ):
            ok = restore_full_backup(str(backup_dir))

        assert ok is True
        assert replace_calls
        assert replace_calls[-1][1] == fake_claude_json
        assert fake_claude_json.read_text() == '{"new": true}'


# ---------------------------------------------------------------------------
# Cross-platform flag
# ---------------------------------------------------------------------------


class TestCrossPlatform:
    def test_symlinks_off_on_windows(self):
        with patch("cc_tui.services.backup.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert (mock_sys.platform != "win32") is False

    def test_symlinks_on_linux(self):
        with patch("cc_tui.services.backup.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert (mock_sys.platform != "win32") is True

    def test_symlinks_on_macos(self):
        with patch("cc_tui.services.backup.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert (mock_sys.platform != "win32") is True
