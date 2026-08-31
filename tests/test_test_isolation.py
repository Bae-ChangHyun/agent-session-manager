from __future__ import annotations

from pathlib import Path

import pytest

from asm import models
from asm.services import agent_import, backup, claude_data, cleaner, migrate, recovery


def test_home_paths_and_trash_are_isolated(
    _isolated_app_data: tuple[Path, Path], real_home_path: Path, tmp_path: Path
) -> None:
    isolated_home, temp_root = _isolated_app_data
    paths = [
        models.CLAUDE_DIR,
        models.CLAUDE_JSON,
        models.PROJECTS_DIR,
        models.APP_DATA_DIR,
        models.BACKUP_BASE_DIR,
        models.RECOVERY_BASE_DIR,
        models.CODEX_DIR,
        models.CODEX_SESSIONS_DIR,
        claude_data.CLAUDE_DIR,
        claude_data.PROJECTS_DIR,
        cleaner.CLAUDE_DIR,
        cleaner._TRASH_LOG,
        recovery.CLAUDE_DIR,
        recovery.RECOVERY_BASE_DIR,
        backup.BACKUP_BASE_DIR,
        agent_import.CLAUDE_JSON,
        agent_import.CODEX_DIR,
        agent_import.CODEX_CONFIG,
        agent_import.CODEX_IMPORT_RECORDS,
    ]
    assert Path.home() == isolated_home
    assert all(path.absolute().is_relative_to(temp_root) for path in paths)
    assert all(path.absolute().is_relative_to(isolated_home) for path in cleaner._ALLOWED_ROOTS)

    forbidden = real_home_path / ".asm" / "must-not-touch"
    for trash in (backup.send2trash, cleaner.send2trash, migrate.send2trash, recovery.send2trash):
        with pytest.raises(AssertionError, match="non-temporary path"):
            trash(str(forbidden))

    disposable = tmp_path / "disposable"
    disposable.mkdir()
    cleaner.send2trash(str(disposable))
    assert not disposable.exists()
