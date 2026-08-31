"""Service for backing up and restoring Claude Code data."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import NamedTuple
from uuid import uuid4

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

_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
_MAX_ARCHIVE_COMPRESSION_RATIO = 200.0


class PluginRestoreWarning(NamedTuple):
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return self.message


class PluginRestoreResult(NamedTuple):
    success: bool
    warnings: list[PluginRestoreWarning]


def _validate_backup_path(path: Path) -> None:
    """Ensure path is within the backup directory."""
    if not path.is_absolute():
        raise ValueError(f"Backup selector must be absolute: {path}")
    resolved = path.resolve()
    base = BACKUP_BASE_DIR.resolve()
    if resolved == base:
        raise ValueError("Backup base directory is not a backup artifact")
    if path != resolved:
        raise ValueError(f"Backup selector aliases another path: {path}")
    if not resolved.is_relative_to(base):
        raise ValueError(f"Backup path outside allowed directory: {path}")


def _ensure_backup_dir() -> Path:
    """Ensure backup directory exists (private — backups may hold OAuth tokens)."""
    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    for d in (BACKUP_BASE_DIR.parent, BACKUP_BASE_DIR):
        d.chmod(0o700)
    return BACKUP_BASE_DIR


def _restrict(path: Path) -> None:
    path.chmod(0o600)


def _restrict_artifact(path: Path) -> None:
    path.chmod(0o700 if path.is_dir() else 0o600)


def _create_private_dir(path: Path) -> None:
    path.mkdir(parents=True)
    path.chmod(0o700)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if not _path_exists(path):
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _discard_artifact(path: Path) -> None:
    try:
        _remove_path(path)
    except OSError as exc:
        logger.error("Failed to remove incomplete artifact %s: %s", path, exc)


def _dir_size(path: Path) -> int:
    """Calculate total size of all files in a directory tree."""
    return sum(
        f.stat().st_size for f in path.rglob("*")
        if f.is_file() and not f.is_symlink()
    )


def _is_safe_tar_member(member: tarfile.TarInfo) -> bool:
    """Return True when an archive member is safe to extract."""
    member_path = PurePosixPath(member.name)
    if (
        not member_path.parts
        or member_path.is_absolute()
        or ".." in member_path.parts
        or "\\" in member.name
    ):
        return False
    if not member.name or member.islnk():
        return False
    return member.isdir() or member.isreg() or member.issym()


def _resolved_archive_link(member_name: str, link_name: str) -> PurePosixPath:
    link = PurePosixPath(link_name)
    if not link.parts or link.is_absolute() or "\\" in link_name:
        raise ValueError(f"External symlink target in archive: {link_name}")
    parts: list[str] = []
    for part in (*PurePosixPath(member_name).parent.parts, *link.parts):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"External symlink target in archive: {link_name}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError(f"External symlink target in archive: {link_name}")
    return PurePosixPath(*parts)


def _is_sensitive_archive_file(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.suffix in {".json", ".jsonl", ".toml"}
        or path.name.startswith(".claude")
        or any(
            part in {"projects", "sessions", "debug", "file-history", "tasks", "todos"}
            for part in path.parts[1:-1]
        )
    )


# ── Create backups ───────────────────────────────────────────────


def create_config_backup() -> str | None:
    """Create a backup of .claude.json. Returns backup path or None."""
    if not CLAUDE_JSON.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    dest = BACKUP_BASE_DIR / "config" / f".claude-{timestamp}.json"
    try:
        backup_dir = _ensure_backup_dir() / "config"
        backup_dir.mkdir(exist_ok=True)
        backup_dir.chmod(0o700)
        shutil.copy2(str(CLAUDE_JSON), str(dest))
        _restrict(dest)
        return str(dest)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create config backup: %s", e)
        _discard_artifact(dest)
        return None


def create_full_backup() -> str | None:
    """Create a full backup of .claude directory and .claude.json."""
    if not CLAUDE_DIR.exists() and not CLAUDE_JSON.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = BACKUP_BASE_DIR / f"full-{timestamp}"

    try:
        _ensure_backup_dir()
        _create_private_dir(backup_dir)
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
        return str(backup_dir)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create full backup: %s", e)
        _discard_artifact(backup_dir)
        return None


def create_settings_backup() -> str | None:
    """Backup settings.json, settings.local.json, keybindings.json."""
    existing = [f for f in SETTINGS_FILES if f.exists()]
    if not existing:
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = BACKUP_BASE_DIR / f"settings-{timestamp}"
    try:
        _ensure_backup_dir()
        _create_private_dir(backup_dir)
        for f in existing:
            shutil.copy2(str(f), str(backup_dir / f.name))
        return str(backup_dir)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create settings backup: %s", e)
        _discard_artifact(backup_dir)
        return None


def create_plugins_backup() -> str | None:
    """Backup plugins/ and skills/ directories (including symlinks)."""
    if not PLUGINS_DIR.exists() and not SKILLS_DIR.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = BACKUP_BASE_DIR / f"plugins-{timestamp}"
    try:
        _ensure_backup_dir()
        _create_private_dir(backup_dir)
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
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create plugins backup: %s", e)
        _discard_artifact(backup_dir)
        return None


def create_sessions_backup() -> str | None:
    """Backup projects/ directory (session data)."""
    if not PROJECTS_DIR.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = BACKUP_BASE_DIR / f"sessions-{timestamp}"
    try:
        _ensure_backup_dir()
        _create_private_dir(backup_dir)
        shutil.copytree(
            str(PROJECTS_DIR),
            str(backup_dir / "projects"),
            symlinks=_SYMLINKS_ON,
            ignore_dangling_symlinks=True,
        )
        return str(backup_dir)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create sessions backup: %s", e)
        _discard_artifact(backup_dir)
        return None


def create_codex_backup() -> str | None:
    """Backup Codex session data (~/.codex/sessions + small index/config files).

    Excludes the large regenerable caches (sqlite logs, generated_images).
    """
    extra_files = [CODEX_DIR / name for name in ("session_index.jsonl", "history.jsonl", "config.toml")]
    if not CODEX_SESSIONS_DIR.exists() and not any(path.exists() for path in extra_files):
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_dir = BACKUP_BASE_DIR / f"codex-{timestamp}"
    try:
        _ensure_backup_dir()
        _create_private_dir(backup_dir)
        if CODEX_SESSIONS_DIR.exists():
            shutil.copytree(
                str(CODEX_SESSIONS_DIR),
                str(backup_dir / "sessions"),
                symlinks=_SYMLINKS_ON,
                ignore_dangling_symlinks=True,
            )
        for f in extra_files:
            if f.exists():
                shutil.copy2(str(f), str(backup_dir / f.name))
        return str(backup_dir)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to create codex backup: %s", e)
        _discard_artifact(backup_dir)
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


def _safety_backup_ready(result: str | None, restore_source: Path) -> bool:
    if not result:
        return False
    path = Path(result)
    try:
        _validate_backup_path(path)
        return _path_exists(path) and path.resolve() != restore_source.resolve()
    except (OSError, ValueError):
        return False


def _copy_path(src: Path, dest: Path) -> None:
    if src.is_symlink():
        dest.symlink_to(src.readlink(), target_is_directory=src.is_dir())
    elif src.is_dir():
        shutil.copytree(
            src,
            dest,
            symlinks=_SYMLINKS_ON,
            ignore_dangling_symlinks=True,
        )
    else:
        shutil.copy2(src, dest, follow_symlinks=False)


def _validate_staged_copy(src: Path, stage: Path) -> None:
    if not _path_exists(stage):
        raise OSError(f"Restore staging failed for {src}")
    if src.is_symlink() != stage.is_symlink():
        raise OSError(f"Restore staging changed path type for {src}")
    if src.is_dir() and not src.is_symlink():
        if not stage.is_dir() or _dir_size(src) != _dir_size(stage):
            raise OSError(f"Restore staging validation failed for {src}")
    elif not src.is_symlink() and src.stat().st_size != stage.stat().st_size:
        raise OSError(f"Restore staging validation failed for {src}")


def _replace_paths_transaction(replacements: list[tuple[Path, Path]]) -> None:
    transaction_id = uuid4().hex
    prepared: list[tuple[Path, Path, Path]] = []
    moved: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for src, dest in replacements:
            dest.parent.mkdir(parents=True, exist_ok=True)
            stage = dest.with_name(f".{dest.name}.asm-stage-{transaction_id}")
            rollback = dest.with_name(f".{dest.name}.asm-rollback-{transaction_id}")
            if _path_exists(stage) or _path_exists(rollback):
                raise FileExistsError(f"Restore transaction path already exists for {dest}")
            prepared.append((dest, stage, rollback))
            _copy_path(src, stage)
            _validate_staged_copy(src, stage)

        for dest, stage, rollback in prepared:
            if _path_exists(dest):
                os.replace(dest, rollback)
                moved.append((dest, rollback))
            os.replace(stage, dest)
            installed.append(dest)
    except (OSError, shutil.Error):
        rollback_errors: list[OSError] = []
        for dest in reversed(installed):
            try:
                _remove_path(dest)
            except OSError as exc:
                rollback_errors.append(exc)
        for dest, rollback in reversed(moved):
            try:
                if _path_exists(dest):
                    _remove_path(dest)
                if _path_exists(rollback):
                    os.replace(rollback, dest)
            except OSError as exc:
                rollback_errors.append(exc)
        for _, stage, _ in prepared:
            _discard_artifact(stage)
        if rollback_errors:
            raise OSError(
                "Restore failed and rollback was incomplete: "
                + "; ".join(str(error) for error in rollback_errors)
            ) from rollback_errors[0]
        raise

    for _, _, rollback in prepared:
        _discard_artifact(rollback)


def restore_config_backup(backup_path: str) -> bool:
    """Restore .claude.json from a backup file."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        if _path_exists(CLAUDE_JSON) and not _safety_backup_ready(create_config_backup(), src):
            raise OSError("Required config safety backup failed")
        _replace_paths_transaction([(src, CLAUDE_JSON)])
        return True
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore config backup: %s", e)
        return False


def restore_full_backup(backup_path: str) -> bool:
    """Restore a full backup with whole-operation rollback."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        replacements = []
        if (src / ".claude").is_dir():
            replacements.append((src / ".claude", CLAUDE_DIR))
        if (src / ".claude.json").is_file():
            replacements.append((src / ".claude.json", CLAUDE_JSON))
        if not replacements:
            return False
        if any(_path_exists(dest) for _, dest in replacements):
            if not _safety_backup_ready(create_full_backup(), src):
                raise OSError("Required full safety backup failed")
        _replace_paths_transaction(replacements)
        return True
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore full backup: %s", e)
        return False


def _replace_dir_with_rollback(src_dir: Path, dest_dir: Path) -> None:
    _replace_paths_transaction([(src_dir, dest_dir)])


def restore_settings_backup(backup_path: str) -> bool:
    """Restore settings files from a backup directory."""
    src = Path(backup_path)
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        allowed = {path.name for path in SETTINGS_FILES}
        replacements = [
            (path, CLAUDE_DIR / path.name)
            for path in src.iterdir()
            if path.is_file() and path.name in allowed
        ]
        if not replacements:
            return False
        if any(_path_exists(dest) for _, dest in replacements):
            if not _safety_backup_ready(create_settings_backup(), src):
                raise OSError("Required settings safety backup failed")
        _replace_paths_transaction(replacements)
        return True
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore settings backup: %s", e)
        return False


def restore_plugins_backup(backup_path: str) -> PluginRestoreResult:
    """Restore plugins/skills from a backup directory.

    Returns (success, list of symlink warnings).
    Symlink-based items are restored but a warning is returned for broken ones.
    """
    src = Path(backup_path)
    if not src.exists():
        return PluginRestoreResult(False, [])
    try:
        _validate_backup_path(src)
        plugins_src = src / "plugins"
        skills_src = src / "skills"
        replacements = []
        if plugins_src.is_dir():
            replacements.append((plugins_src, PLUGINS_DIR))
        if skills_src.is_dir():
            replacements.append((skills_src, SKILLS_DIR))
        if not replacements:
            return PluginRestoreResult(False, [])
        if any(_path_exists(dest) for _, dest in replacements):
            if not _safety_backup_ready(create_plugins_backup(), src):
                raise OSError("Required plugins safety backup failed")
        _replace_paths_transaction(replacements)
        warnings: list[PluginRestoreWarning] = []
        for _, restored_path in replacements:
            try:
                warnings.extend(
                    PluginRestoreWarning("broken_symlink", str(restored_path), item)
                    for item in detect_broken_symlinks(restored_path)
                )
            except (OSError, ValueError, RuntimeError) as exc:
                warnings.append(
                    PluginRestoreWarning(
                        "post_restore_diagnostic_failed",
                        str(restored_path),
                        f"Could not inspect restored symlinks under {restored_path}: {exc}",
                    )
                )
        return PluginRestoreResult(True, warnings)
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore plugins backup: %s", e)
        return PluginRestoreResult(False, [])


def restore_sessions_backup(backup_path: str) -> bool:
    """Restore projects/ directory from a backup."""
    src = Path(backup_path)
    projects_src = src / "projects"
    if not src.exists() or not projects_src.exists():
        return False
    try:
        _validate_backup_path(src)
        if _path_exists(PROJECTS_DIR) and not _safety_backup_ready(create_sessions_backup(), src):
            raise OSError("Required sessions safety backup failed")
        _replace_dir_with_rollback(projects_src, PROJECTS_DIR)
        return True
    except (OSError, ValueError, shutil.Error) as e:
        logger.warning("Failed to restore sessions backup: %s", e)
        return False


def restore_codex_backup(backup_path: str) -> bool:
    """Restore ~/.codex/sessions (and index/config files) from a codex backup."""
    src = Path(backup_path)
    sessions_src = src / "sessions"
    if not src.exists():
        return False
    try:
        _validate_backup_path(src)
        replacements = []
        if sessions_src.is_dir():
            replacements.append((sessions_src, CODEX_SESSIONS_DIR))
        for name in ("session_index.jsonl", "history.jsonl", "config.toml"):
            f = src / name
            if f.is_file():
                replacements.append((f, CODEX_DIR / name))
        if not replacements:
            return False
        if any(_path_exists(dest) for _, dest in replacements):
            if not _safety_backup_ready(create_codex_backup(), src):
                raise OSError("Required Codex safety backup failed")
        _replace_paths_transaction(replacements)
        return True
    except (OSError, ValueError, shutil.Error) as e:
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

        temp_path = out_dir / f".{archive_path.name}.{uuid4().hex}.part"
        with tarfile.open(str(temp_path), "w:gz") as tar:
            tar.add(str(src), arcname=src.name)
        with tarfile.open(str(temp_path), "r:gz") as tar:
            _validate_archive(temp_path, tar.getmembers())
        _restrict(temp_path)
        os.replace(temp_path, archive_path)

        return str(archive_path)
    except (OSError, ValueError, tarfile.TarError) as e:
        logger.warning("Failed to export backup: %s", e)
        if "temp_path" in locals():
            _discard_artifact(temp_path)
        return None


def _validate_archive(
    src: Path, members: list[tarfile.TarInfo]
) -> tuple[str, list[tarfile.TarInfo]]:
    if not members:
        raise ValueError("Archive is empty")
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise ValueError(
            f"Archive has {len(members)} members; limit is {_MAX_ARCHIVE_MEMBERS}"
        )

    names: set[str] = set()
    symlink_names: set[str] = set()
    top_names: set[str] = set()
    total_bytes = 0
    for member in members:
        if not _is_safe_tar_member(member):
            raise ValueError(f"Unsafe archive member: {member.name}")
        normalized = str(PurePosixPath(member.name))
        if normalized in names:
            raise ValueError(f"Duplicate archive member: {member.name}")
        names.add(normalized)
        if member.issym():
            symlink_names.add(normalized)
        top_names.add(PurePosixPath(normalized).parts[0])
        if member.isreg():
            if member.size < 0 or member.size > _MAX_ARCHIVE_MEMBER_BYTES:
                raise ValueError(
                    f"Archive member {member.name} is {member.size} bytes; "
                    f"limit is {_MAX_ARCHIVE_MEMBER_BYTES}"
                )
            total_bytes += member.size

    for name in names:
        parts = PurePosixPath(name).parts
        has_symlink_parent = any(
            str(PurePosixPath(*parts[:index])) in symlink_names
            for index in range(1, len(parts))
        )
        if has_symlink_parent:
            raise ValueError(f"Archive member has a symlink parent: {name}")

    if len(top_names) != 1:
        raise ValueError("Archive must contain exactly one top-level backup")
    top = next(iter(top_names))
    for member in members:
        if member.issym():
            target = _resolved_archive_link(member.name, member.linkname)
            if target.parts[0] != top:
                raise ValueError(
                    f"Symlink target escapes archive root: {member.name} -> {member.linkname}"
                )
    if total_bytes > _MAX_ARCHIVE_TOTAL_BYTES:
        raise ValueError(
            f"Archive expands to {total_bytes} bytes; limit is {_MAX_ARCHIVE_TOTAL_BYTES}"
        )
    compressed_bytes = src.stat().st_size
    ratio = total_bytes / compressed_bytes if compressed_bytes else float("inf")
    if ratio > _MAX_ARCHIVE_COMPRESSION_RATIO:
        raise ValueError(
            f"Archive compression ratio is {ratio:.1f}; "
            f"limit is {_MAX_ARCHIVE_COMPRESSION_RATIO:.1f}"
        )
    return top_names.pop(), members


def _extract_archive(
    archive: tarfile.TarFile, members: list[tarfile.TarInfo], destination: Path
) -> None:
    directories = [member for member in members if member.isdir()]
    files = [member for member in members if member.isreg()]
    symlinks = [member for member in members if member.issym()]

    for member in sorted(directories, key=lambda item: len(PurePosixPath(item.name).parts)):
        target = destination.joinpath(*PurePosixPath(member.name).parts)
        target.mkdir(parents=True, exist_ok=True)
    for member in files:
        target = destination.joinpath(*PurePosixPath(member.name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise tarfile.ExtractError(f"Could not read archive member: {member.name}")
        with source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        if target.stat().st_size != member.size:
            raise tarfile.ExtractError(f"Archive member size mismatch: {member.name}")
        mode = member.mode & 0o777
        if _is_sensitive_archive_file(member.name):
            mode = (mode & 0o100) | 0o600
        target.chmod(mode)
    for member in symlinks:
        target = destination.joinpath(*PurePosixPath(member.name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(member.linkname)
    for member in sorted(
        directories,
        key=lambda item: len(PurePosixPath(item.name).parts),
        reverse=True,
    ):
        destination.joinpath(*PurePosixPath(member.name).parts).chmod(member.mode & 0o777)


def import_backup(archive_path: str) -> str | None:
    """Import a .tar.gz backup into the backup directory.

    Returns the extracted backup path or None on failure.
    """
    src = Path(archive_path)
    if not src.exists() or not src.name.endswith(".tar.gz"):
        return None
    staging: Path | None = None
    try:
        backup_dir = _ensure_backup_dir()
        staging = backup_dir / f".importing-{uuid4().hex}"
        staging.mkdir(mode=0o700)
        with tarfile.open(str(src), "r:gz") as tar:
            top, members = _validate_archive(src, tar.getmembers())
            _extract_archive(tar, members, staging)

        staged_top = staging / top
        if staged_top.is_file() and staged_top.suffix == ".json":
            final = backup_dir / "config" / top
            final.parent.mkdir(exist_ok=True)
            final.parent.chmod(0o700)
        else:
            if staged_top.is_symlink() or not staged_top.is_dir():
                raise ValueError("Archive top-level item is not a backup directory")
            if not any(top.startswith(prefix) for prefix in (
                "full-", "settings-", "plugins-", "sessions-", "codex-"
            )):
                raise ValueError(f"Unsupported backup name: {top}")
            final = backup_dir / top
        if _path_exists(final):
            raise FileExistsError(f"Backup already exists: {final}")
        _restrict_artifact(staged_top)
        os.replace(staged_top, final)
        _discard_artifact(staging)
        return str(final)
    except (OSError, ValueError, tarfile.TarError, shutil.Error) as e:
        logger.warning("Failed to import backup: %s", e)
        if staging is not None:
            _discard_artifact(staging)
        return None
