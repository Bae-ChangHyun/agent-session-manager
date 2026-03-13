"""Service for backing up and restoring Claude Code data."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from cc_tui.models import BACKUP_BASE_DIR, CLAUDE_DIR, CLAUDE_JSON, BackupInfo


def _ensure_backup_dir() -> Path:
    """Ensure backup directory exists."""
    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_BASE_DIR


def create_config_backup() -> str | None:
    """Create a backup of .claude.json. Returns backup path or None."""
    if not CLAUDE_JSON.exists():
        return None
    backup_dir = _ensure_backup_dir() / "config"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = backup_dir / f".claude-{timestamp}.json"
    try:
        shutil.copy2(str(CLAUDE_JSON), str(dest))
        return str(dest)
    except OSError:
        return None


def create_full_backup() -> str | None:
    """Create a full backup of .claude directory and .claude.json."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = _ensure_backup_dir() / f"full-{timestamp}"

    try:
        # Backup .claude directory
        if CLAUDE_DIR.exists():
            shutil.copytree(
                str(CLAUDE_DIR),
                str(backup_dir / ".claude"),
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
        # Backup .claude.json
        if CLAUDE_JSON.exists():
            shutil.copy2(str(CLAUDE_JSON), str(backup_dir / ".claude.json"))
        return str(backup_dir)
    except OSError:
        return None


def list_backups() -> list[BackupInfo]:
    """List all available backups."""
    backup_dir = _ensure_backup_dir()
    result = []

    # Config backups
    config_dir = backup_dir / "config"
    if config_dir.exists():
        for f in sorted(config_dir.iterdir(), reverse=True):
            if f.suffix == ".json":
                stat = f.stat()
                result.append(
                    BackupInfo(
                        name=f"[config] {f.name}",
                        path=str(f),
                        created=stat.st_mtime,
                        size_bytes=stat.st_size,
                    )
                )

    # Full backups
    for d in sorted(backup_dir.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("full-"):
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            stat = d.stat()
            result.append(
                BackupInfo(
                    name=f"[full] {d.name}",
                    path=str(d),
                    created=stat.st_mtime,
                    size_bytes=size,
                )
            )

    result.sort(key=lambda b: b.created, reverse=True)
    return result


def restore_config_backup(backup_path: str) -> bool:
    """Restore .claude.json from a backup file."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        # Create a backup of current before restoring
        create_config_backup()
        shutil.copy2(str(src), str(CLAUDE_JSON))
        return True
    except OSError:
        return False


def restore_full_backup(backup_path: str) -> bool:
    """Restore a full backup."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        # Create FULL backup of current state before restoring (not just config)
        create_full_backup()

        claude_backup = src / ".claude"
        json_backup = src / ".claude.json"

        if claude_backup.exists():
            if CLAUDE_DIR.exists():
                shutil.rmtree(str(CLAUDE_DIR))
            shutil.copytree(str(claude_backup), str(CLAUDE_DIR), symlinks=True)

        if json_backup.exists():
            shutil.copy2(str(json_backup), str(CLAUDE_JSON))

        return True
    except OSError:
        return False


def delete_backup(backup_path: str) -> bool:
    """Delete a backup."""
    p = Path(backup_path)
    if not p.exists():
        return False
    try:
        if p.is_dir():
            shutil.rmtree(str(p))
        else:
            p.unlink()
        return True
    except OSError:
        return False
