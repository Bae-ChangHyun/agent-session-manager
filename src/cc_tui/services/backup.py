"""Service for backing up and restoring Claude Code data."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from cc_tui.models import BACKUP_BASE_DIR, CLAUDE_DIR, CLAUDE_JSON, BackupInfo

logger = logging.getLogger(__name__)


def _validate_backup_path(path: Path) -> None:
    """Ensure path is within the backup directory."""
    resolved = path.resolve()
    if not resolved.is_relative_to(BACKUP_BASE_DIR.resolve()):
        raise ValueError(f"Backup path outside allowed directory: {path}")


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
    except OSError as e:
        logger.warning("Failed to create config backup: %s", e)
        return None


def create_full_backup() -> str | None:
    """Create a full backup of .claude directory and .claude.json."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = _ensure_backup_dir() / f"full-{timestamp}"

    try:
        if CLAUDE_DIR.exists():
            shutil.copytree(
                str(CLAUDE_DIR),
                str(backup_dir / ".claude"),
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
        if CLAUDE_JSON.exists():
            shutil.copy2(str(CLAUDE_JSON), str(backup_dir / ".claude.json"))
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create full backup: %s", e)
        return None


def list_backups() -> list[BackupInfo]:
    """List all available backups."""
    backup_dir = _ensure_backup_dir()
    result = []

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
        _validate_backup_path(src)
        create_config_backup()
        shutil.copy2(str(src), str(CLAUDE_JSON))
        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore config backup: %s", e)
        return False


def restore_full_backup(backup_path: str) -> bool:
    """Restore a full backup with rename+rollback for safety.

    Both .claude directory and .claude.json are restored atomically --
    if either step fails, both are rolled back.
    """
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        safety = create_full_backup()
        if safety is None:
            return False

        claude_backup = src / ".claude"
        json_backup = src / ".claude.json"
        temp_dir = CLAUDE_DIR.with_name(".claude.restoring")
        temp_json = CLAUDE_JSON.with_suffix(".restoring")

        # Phase 1: Prepare .claude.json copy to temp (validate before touching anything)
        if json_backup.exists():
            try:
                shutil.copy2(str(json_backup), str(temp_json))
            except OSError:
                if temp_json.exists():
                    temp_json.unlink()
                raise

        # Phase 2: Replace .claude directory with rename+rollback
        if claude_backup.exists():
            if temp_dir.exists():
                shutil.rmtree(str(temp_dir))
            if CLAUDE_DIR.exists():
                CLAUDE_DIR.rename(temp_dir)
            try:
                shutil.copytree(str(claude_backup), str(CLAUDE_DIR), symlinks=False)
            except Exception:
                # Rollback directory
                if temp_dir.exists():
                    if CLAUDE_DIR.exists():
                        try:
                            shutil.rmtree(str(CLAUDE_DIR))
                        except OSError as rmtree_err:
                            logger.error(
                                "Rollback: failed to remove partial .claude dir: %s. "
                                "Original data preserved at %s",
                                rmtree_err, temp_dir,
                            )
                            if temp_json.exists():
                                temp_json.unlink()
                            raise
                    temp_dir.rename(CLAUDE_DIR)
                if temp_json.exists():
                    temp_json.unlink()
                raise

        # Phase 3: Atomically move .claude.json (rename is atomic on same filesystem)
        if temp_json.exists():
            temp_json.rename(CLAUDE_JSON)

        # Phase 4: Cleanup
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir))

        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore full backup: %s", e)
        return False


def delete_backup(backup_path: str) -> bool:
    """Delete a backup (moves to OS trash for safety)."""
    p = Path(backup_path)
    if not p.exists():
        return False
    try:
        _validate_backup_path(p)
        send2trash(str(p))
        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to delete backup: %s", e)
        return False
