"""Service for backing up and restoring Claude Code data."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from asm.models import (
    BACKUP_BASE_DIR,
    CLAUDE_DIR,
    CLAUDE_JSON,
    CODEX_DIR,
    CODEX_SESSIONS_DIR,
    PLUGINS_DIR,
    PROJECTS_DIR,
    SKILLS_DIR,
    BackupInfo,
)

logger = logging.getLogger(__name__)

# Settings files to back up
SETTINGS_FILES = [
    CLAUDE_DIR / "settings.json",
    CLAUDE_DIR / "settings.local.json",
    CLAUDE_DIR / "keybindings.json",
]

_SYMLINKS_ON = sys.platform != "win32"


def _validate_backup_path(path: Path) -> None:
    """Ensure path is within the backup directory."""
    resolved = path.resolve()
    if not resolved.is_relative_to(BACKUP_BASE_DIR.resolve()):
        raise ValueError(f"Backup path outside allowed directory: {path}")


def _ensure_backup_dir() -> Path:
    """Ensure backup directory exists (private — backups may hold OAuth tokens)."""
    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    # ~/.asm tree may contain ~/.claude.json (OAuth tokens) — keep it owner-only.
    for d in (BACKUP_BASE_DIR.parent, BACKUP_BASE_DIR):
        try:
            d.chmod(0o700)
        except OSError:
            pass
    return BACKUP_BASE_DIR


def _restrict(path: Path) -> None:
    """Best-effort owner-only (0600) on a possibly-sensitive backup file."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _dir_size(path: Path) -> int:
    """Calculate total size of all files in a directory tree."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _is_safe_tar_member(member: tarfile.TarInfo) -> bool:
    """Return True when an archive member is safe to extract."""
    member_path = Path(member.name)
    if member_path.is_absolute() or ".." in member_path.parts:
        return False
    if member.issym() or member.islnk():
        return False
    if member.isdev():
        return False
    return True


# ── Create backups ───────────────────────────────────────────────


def create_config_backup() -> str | None:
    """Create a backup of .claude.json. Returns backup path or None."""
    if not CLAUDE_JSON.exists():
        return None
    backup_dir = _ensure_backup_dir() / "config"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    dest = backup_dir / f".claude-{timestamp}.json"
    try:
        shutil.copy2(str(CLAUDE_JSON), str(dest))
        _restrict(dest)  # contains OAuth tokens
        return str(dest)
    except OSError as e:
        logger.warning("Failed to create config backup: %s", e)
        return None


def create_full_backup() -> str | None:
    """Create a full backup of .claude directory and .claude.json."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = _ensure_backup_dir() / f"full-{timestamp}"

    try:
        if CLAUDE_DIR.exists():
            shutil.copytree(
                str(CLAUDE_DIR),
                str(backup_dir / ".claude"),
                symlinks=_SYMLINKS_ON,
                ignore_dangling_symlinks=True,
            )
        if CLAUDE_JSON.exists():
            json_dest = backup_dir / ".claude.json"
            shutil.copy2(str(CLAUDE_JSON), str(json_dest))
            _restrict(json_dest)  # contains OAuth tokens
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create full backup: %s", e)
        return None


def create_settings_backup() -> str | None:
    """Backup settings.json, settings.local.json, keybindings.json."""
    existing = [f for f in SETTINGS_FILES if f.exists()]
    if not existing:
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = _ensure_backup_dir() / f"settings-{timestamp}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for f in existing:
            shutil.copy2(str(f), str(backup_dir / f.name))
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create settings backup: %s", e)
        if backup_dir.exists():
            shutil.rmtree(str(backup_dir), ignore_errors=True)
        return None


def create_plugins_backup() -> str | None:
    """Backup plugins/ and skills/ directories (including symlinks)."""
    if not PLUGINS_DIR.exists() and not SKILLS_DIR.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = _ensure_backup_dir() / f"plugins-{timestamp}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if PLUGINS_DIR.exists():
            shutil.copytree(
                str(PLUGINS_DIR),
                str(backup_dir / "plugins"),
                symlinks=_SYMLINKS_ON,
                ignore_dangling_symlinks=True,
            )
        if SKILLS_DIR.exists():
            shutil.copytree(
                str(SKILLS_DIR),
                str(backup_dir / "skills"),
                symlinks=_SYMLINKS_ON,
                ignore_dangling_symlinks=True,
            )
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create plugins backup: %s", e)
        if backup_dir.exists():
            shutil.rmtree(str(backup_dir), ignore_errors=True)
        return None


def create_sessions_backup() -> str | None:
    """Backup projects/ directory (session data)."""
    if not PROJECTS_DIR.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = _ensure_backup_dir() / f"sessions-{timestamp}"
    try:
        shutil.copytree(
            str(PROJECTS_DIR),
            str(backup_dir / "projects"),
            symlinks=_SYMLINKS_ON,
            ignore_dangling_symlinks=True,
        )
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create sessions backup: %s", e)
        if backup_dir.exists():
            shutil.rmtree(str(backup_dir), ignore_errors=True)
        return None


def create_codex_backup() -> str | None:
    """Backup Codex session data (~/.codex/sessions + small index/config files).

    Excludes the large regenerable caches (sqlite logs, generated_images).
    """
    if not CODEX_SESSIONS_DIR.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = _ensure_backup_dir() / f"codex-{timestamp}"
    try:
        shutil.copytree(
            str(CODEX_SESSIONS_DIR),
            str(backup_dir / "sessions"),
            symlinks=_SYMLINKS_ON,
            ignore_dangling_symlinks=True,
        )
        for name in ("session_index.jsonl", "history.jsonl", "config.toml"):
            f = CODEX_DIR / name
            if f.exists():
                shutil.copy2(str(f), str(backup_dir / name))
        return str(backup_dir)
    except OSError as e:
        logger.warning("Failed to create codex backup: %s", e)
        if backup_dir.exists():
            shutil.rmtree(str(backup_dir), ignore_errors=True)
        return None


# ── List backups ─────────────────────────────────────────────────


def list_backups() -> list[BackupInfo]:
    """List all available backups."""
    backup_dir = _ensure_backup_dir()
    result = []

    # Config backups (single files in config/)
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
                        backup_type="config",
                    )
                )

    # Directory-based backups: full, settings, plugins, sessions
    _TYPE_PREFIXES = {
        "full-": "full",
        "settings-": "settings",
        "plugins-": "plugins",
        "sessions-": "sessions",
        "codex-": "codex",
    }
    for d in sorted(backup_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        for prefix, btype in _TYPE_PREFIXES.items():
            if d.name.startswith(prefix):
                size = _dir_size(d)
                stat = d.stat()
                result.append(
                    BackupInfo(
                        name=f"[{btype}] {d.name}",
                        path=str(d),
                        created=stat.st_mtime,
                        size_bytes=size,
                        backup_type=btype,
                    )
                )
                break

    result.sort(key=lambda b: b.created, reverse=True)
    return result


# ── Symlink detection ────────────────────────────────────────────


def detect_symlinks(path: Path) -> list[str]:
    """Find all symlinks in a directory tree. Returns list of relative path strings."""
    symlinks = []
    if not path.exists():
        return symlinks
    for item in path.rglob("*"):
        if item.is_symlink():
            target = str(item.resolve()) if item.exists() else "(broken)"
            rel = str(item.relative_to(path))
            symlinks.append(f"{rel} -> {target}")
    return symlinks


def detect_broken_symlinks(path: Path) -> list[str]:
    """Find symlinks whose targets don't exist. Returns list of relative path strings."""
    broken = []
    if not path.exists():
        return broken
    for item in path.rglob("*"):
        if item.is_symlink():
            target = item.resolve()
            if not target.exists():
                rel = str(item.relative_to(path))
                raw_target = str(Path(str(item)).readlink())
                broken.append(f"{rel} -> {raw_target}")
    return broken


# ── Restore backups ──────────────────────────────────────────────


def restore_config_backup(backup_path: str) -> bool:
    """Restore .claude.json from a backup file."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        # Read the backup up front: the safety backup below can land on the same
        # timestamped filename as ``src`` (second resolution) and overwrite it
        # with the current — possibly broken — config before we copy it back.
        payload = src.read_bytes()
        create_config_backup()
        CLAUDE_JSON.write_bytes(payload)
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
        temp_json = CLAUDE_JSON.with_name(f"{CLAUDE_JSON.name}.restoring")

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
                shutil.copytree(
                    str(claude_backup), str(CLAUDE_DIR),
                    symlinks=_SYMLINKS_ON, ignore_dangling_symlinks=True,
                )
            except (OSError, shutil.Error):
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
            os.replace(temp_json, CLAUDE_JSON)

        # Phase 4: Cleanup
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir))

        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore full backup: %s", e)
        return False


def _replace_dir_with_rollback(src_dir: Path, dest_dir: Path) -> None:
    """Replace dest_dir with a copy of src_dir, rolling back on failure.

    The live dir is renamed aside first; if the copy fails the original is
    restored, so a mid-copy error never leaves the user with no data.
    """
    temp = dest_dir.with_name(dest_dir.name + ".restoring")
    if temp.exists():
        shutil.rmtree(str(temp))
    moved = False
    if dest_dir.exists():
        dest_dir.rename(temp)
        moved = True
    try:
        shutil.copytree(
            str(src_dir), str(dest_dir),
            symlinks=_SYMLINKS_ON, ignore_dangling_symlinks=True,
        )
    except (OSError, shutil.Error):
        if moved:
            if dest_dir.exists():
                shutil.rmtree(str(dest_dir), ignore_errors=True)
            temp.rename(dest_dir)
        raise
    if moved and temp.exists():
        shutil.rmtree(str(temp), ignore_errors=True)


def restore_settings_backup(backup_path: str) -> bool:
    """Restore settings files from a backup directory."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        # Safety: backup current settings first
        create_settings_backup()
        for f in src.iterdir():
            if f.is_file() and f.suffix == ".json":
                dest = CLAUDE_DIR / f.name
                shutil.copy2(str(f), str(dest))
        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore settings backup: %s", e)
        return False


def restore_plugins_backup(backup_path: str) -> tuple[bool, list[str]]:
    """Restore plugins/skills from a backup directory.

    Returns (success, list of symlink warnings).
    Symlink-based items are restored but a warning is returned for broken ones.
    """
    src = Path(backup_path)
    if not src.exists():
        return False, []
    try:
        _validate_backup_path(src)
        # Safety: backup current plugins first
        create_plugins_backup()

        plugins_src = src / "plugins"
        skills_src = src / "skills"

        if plugins_src.exists():
            _replace_dir_with_rollback(plugins_src, PLUGINS_DIR)

        if skills_src.exists():
            _replace_dir_with_rollback(skills_src, SKILLS_DIR)

        # Detect broken symlinks after restore
        broken = []
        broken.extend(detect_broken_symlinks(PLUGINS_DIR))
        broken.extend(detect_broken_symlinks(SKILLS_DIR))

        return True, broken
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore plugins backup: %s", e)
        return False, []


def restore_sessions_backup(backup_path: str) -> bool:
    """Restore projects/ directory from a backup."""
    src = Path(backup_path)
    projects_src = src / "projects"
    if not src.exists() or not projects_src.exists():
        return False
    try:
        _validate_backup_path(src)
        # Safety: backup current sessions first
        create_sessions_backup()

        _replace_dir_with_rollback(projects_src, PROJECTS_DIR)
        return True
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore sessions backup: %s", e)
        return False


def restore_codex_backup(backup_path: str) -> bool:
    """Restore ~/.codex/sessions (and index/config files) from a codex backup."""
    src = Path(backup_path)
    sessions_src = src / "sessions"
    if not src.exists() or not sessions_src.exists():
        return False
    try:
        _validate_backup_path(src)
        # Safety: back up current Codex sessions first.
        create_codex_backup()

        if CODEX_SESSIONS_DIR.exists():
            shutil.rmtree(str(CODEX_SESSIONS_DIR))
        shutil.copytree(
            str(sessions_src), str(CODEX_SESSIONS_DIR),
            symlinks=_SYMLINKS_ON,
            ignore_dangling_symlinks=True,
        )
        for name in ("session_index.jsonl", "history.jsonl", "config.toml"):
            f = src / name
            if f.exists():
                shutil.copy2(str(f), str(CODEX_DIR / name))
        return True
    except (OSError, ValueError) as e:
        logger.warning("Failed to restore codex backup: %s", e)
        return False


# ── Delete backup ────────────────────────────────────────────────


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


# ── Export / Import ──────────────────────────────────────────────


def export_backup(backup_path: str, dest_dir: str | None = None) -> str | None:
    """Export a backup as .tar.gz for server migration.

    Args:
        backup_path: Path to the backup (file or directory).
        dest_dir: Where to write the archive. Defaults to ~/Desktop or home.

    Returns:
        Path to the created .tar.gz or None on failure.
    """
    src = Path(backup_path)
    if not src.exists():
        return None
    try:
        _validate_backup_path(src)
        if dest_dir:
            out_dir = Path(dest_dir)
        else:
            desktop = Path.home() / "Desktop"
            out_dir = desktop if desktop.exists() else Path.home()
        out_dir.mkdir(parents=True, exist_ok=True)

        archive_name = src.name if src.is_dir() else src.stem
        archive_path = out_dir / f"{archive_name}.tar.gz"

        # Avoid overwrite
        counter = 1
        while archive_path.exists():
            archive_path = out_dir / f"{archive_name}_{counter}.tar.gz"
            counter += 1

        with tarfile.open(str(archive_path), "w:gz") as tar:
            tar.add(str(src), arcname=src.name)
        # May bundle ~/.claude.json (OAuth tokens) — don't leave it world-readable.
        _restrict(archive_path)

        return str(archive_path)
    except (OSError, ValueError, tarfile.TarError) as e:
        logger.warning("Failed to export backup: %s", e)
        return None


def import_backup(archive_path: str) -> str | None:
    """Import a .tar.gz backup into the backup directory.

    Returns the extracted backup path or None on failure.
    """
    src = Path(archive_path)
    if not src.exists() or not src.name.endswith(".tar.gz"):
        return None
    try:
        backup_dir = _ensure_backup_dir()

        with tarfile.open(str(src), "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                if not _is_safe_tar_member(member):
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            # Python 3.12+ supports filter param; older versions don't
            try:
                tar.extractall(path=str(backup_dir), members=members, filter="data")
            except TypeError:
                tar.extractall(path=str(backup_dir), members=members)

        # Determine the extracted name (first component of archive contents)
        with tarfile.open(str(src), "r:gz") as tar:
            names = tar.getnames()
            if names:
                top = names[0].split("/")[0]
                return str(backup_dir / top)
        return None
    except (OSError, ValueError, tarfile.TarError) as e:
        logger.warning("Failed to import backup: %s", e)
        return None
