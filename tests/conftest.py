"""Shared test fixtures."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from asm import models
from asm.services import backup, cleaner, pricing, recovery


_REAL_HOME = Path.home().absolute()


def _under(path: Path, root: Path) -> bool:
    try:
        return path.expanduser().absolute().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _replace_home_path(path: Path, isolated_home: Path) -> Path:
    return isolated_home / path.expanduser().absolute().relative_to(_REAL_HOME)


def _isolate_loaded_paths(monkeypatch, isolated_home: Path) -> None:
    for module_name, module in list(sys.modules.items()):
        if module is None or not module_name.startswith("asm"):
            continue
        for name, value in list(vars(module).items()):
            if isinstance(value, Path) and _under(value, _REAL_HOME):
                monkeypatch.setattr(module, name, _replace_home_path(value, isolated_home))
            elif isinstance(value, tuple) and value and all(isinstance(v, Path) for v in value):
                replaced = tuple(
                    _replace_home_path(v, isolated_home) if _under(v, _REAL_HOME) else v
                    for v in value
                )
                monkeypatch.setattr(module, name, replaced)
            elif isinstance(value, list) and value and all(isinstance(v, Path) for v in value):
                replaced = [
                    _replace_home_path(v, isolated_home) if _under(v, _REAL_HOME) else v
                    for v in value
                ]
                monkeypatch.setattr(module, name, replaced)


@pytest.fixture(autouse=True)
def _isolated_app_data(monkeypatch, tmp_path_factory):
    isolated_home = tmp_path_factory.mktemp("asm-home")
    app_data_dir = tmp_path_factory.mktemp("asm-app-data")
    temp_root = tmp_path_factory.getbasetemp().absolute()
    backup_dir = app_data_dir / "backups"
    recovery_dir = app_data_dir / "recovery"

    def safe_test_trash(path: str) -> None:
        target = Path(path).absolute()
        if not target.is_relative_to(temp_root):
            raise AssertionError(f"Test attempted to trash a non-temporary path: {target}")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("CODEX_HOME", str(isolated_home / ".codex"))
    monkeypatch.setenv("ASM_CODEX_HOMES", str(isolated_home / ".codex"))
    monkeypatch.setattr(models, "APP_DATA_DIR", app_data_dir)
    monkeypatch.setattr(models, "BACKUP_BASE_DIR", backup_dir)
    monkeypatch.setattr(models, "RECOVERY_BASE_DIR", recovery_dir)
    monkeypatch.setattr(models, "_codex_home_override", None)
    monkeypatch.setattr(backup, "BACKUP_BASE_DIR", backup_dir)
    monkeypatch.setattr(recovery, "RECOVERY_BASE_DIR", recovery_dir)
    monkeypatch.setattr(cleaner, "_TRASH_LOG", app_data_dir / "trash-log.jsonl")
    _isolate_loaded_paths(monkeypatch, isolated_home)

    from asm.services import migrate

    for module in (backup, cleaner, migrate, recovery):
        monkeypatch.setattr(module, "send2trash", safe_test_trash)
    return isolated_home, temp_root


@pytest.fixture
def real_home_path():
    return _REAL_HOME


@pytest.fixture(autouse=True)
def _no_live_pricing(monkeypatch):
    monkeypatch.setattr(pricing, "_live_db", {})
    monkeypatch.setattr(pricing, "_rates_source", "bundled table")
