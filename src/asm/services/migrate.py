"""Service for migrating Claude Code sessions between projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from send2trash import send2trash

from asm import models
from asm.models import PROJECTS_DIR, encode_path


class ProjectPathResolutionError(ValueError):
    pass


class PathRewriteError(RuntimeError):
    pass


class MigrationValidationError(ValueError):
    pass


class MigrationApplyError(RuntimeError):
    pass


@dataclass
class MigrateResult:
    """Result of a migration operation."""

    success: bool
    sessions_copied: int = 0
    sessions_skipped: int = 0
    memory_copied: bool = False
    message: str = ""


@dataclass(frozen=True)
class TargetReplacementScope:
    sessions: int
    memory_files: int
    has_index: bool
    other_entries: int
    total_bytes: int


_SOURCE_PATH_FIELDS = {"cwd", "projectPath", "projectDir", "workingDirectory"}
_INDEX_PATH_FIELDS = _SOURCE_PATH_FIELDS | {"fullPath", "filePath"}


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or (
        len(value) > 2 and value[0].isalpha() and value[1] == ":" and value[2] in "\\/"
    )


def _normalized_path(value: str) -> str:
    normalized = os.path.normpath(value)
    return normalized.casefold() if len(normalized) > 1 and normalized[1] == ":" else normalized


def _recorded_project_paths(encoded: str) -> set[str]:
    found: set[str] = set()
    for session_file in sorted((PROJECTS_DIR / encoded).glob("*.jsonl")):
        if session_file.is_symlink():
            raise ProjectPathResolutionError(f"Session metadata is a symlink: {session_file}")
        try:
            with session_file.open() as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    for key in _SOURCE_PATH_FIELDS:
                        value = obj.get(key)
                        if (
                            isinstance(value, str)
                            and _is_absolute_path(value)
                            and encode_path(value) == encoded
                        ):
                            found.add(value)
        except OSError as exc:
            raise ProjectPathResolutionError(
                f"Cannot read session metadata for actual path: {session_file}: {exc}"
            ) from exc

    if models.CLAUDE_JSON.exists():
        try:
            data = json.loads(models.CLAUDE_JSON.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectPathResolutionError(
                f"Cannot read project registry for actual path: {models.CLAUDE_JSON}: {exc}"
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("projects", {}), dict):
            raise ProjectPathResolutionError(
                f"Cannot read project registry for actual path: {models.CLAUDE_JSON}: invalid schema"
            )
        found.update(
            path
            for path in data.get("projects", {})
            if isinstance(path, str)
            and _is_absolute_path(path)
            and encode_path(path) == encoded
        )
    return found


def resolve_project_path(encoded: str) -> str:
    found = _recorded_project_paths(encoded)
    if len(found) == 1:
        return next(iter(found))
    if not found:
        raise ProjectPathResolutionError(
            f"Cannot resolve actual path for Claude project directory {encoded}"
        )
    raise ProjectPathResolutionError(
        f"Ambiguous actual path for Claude project directory {encoded}: {', '.join(sorted(found))}"
    )


def _validate_encoded_path(actual_path: str, encoded: str, role: str) -> None:
    if not _is_absolute_path(actual_path):
        raise MigrationValidationError(f"{role} path must be absolute: {actual_path}")
    if not encoded or Path(encoded).name != encoded or encoded in {".", ".."}:
        raise MigrationValidationError(f"Invalid {role.lower()} encoded directory: {encoded}")
    expected = encode_path(actual_path)
    if encoded != expected:
        raise MigrationValidationError(
            f"{role} encoded directory does not match path: {encoded} != {expected}"
        )


def _validate_project_dir(project_dir: Path, role: str, must_exist: bool) -> None:
    try:
        root = PROJECTS_DIR.resolve(strict=True)
    except OSError as exc:
        raise MigrationValidationError(f"Claude projects directory is unavailable: {exc}") from exc
    if not root.is_dir():
        raise MigrationValidationError(f"Claude projects path is not a directory: {root}")
    if project_dir.parent != PROJECTS_DIR:
        raise MigrationValidationError(f"{role} is not a direct Claude project directory: {project_dir}")
    if project_dir.is_symlink():
        raise MigrationValidationError(f"{role} project directory is a symlink: {project_dir}")
    if not project_dir.exists():
        if must_exist:
            raise MigrationValidationError(f"{role} project directory does not exist: {project_dir}")
        return
    if not project_dir.is_dir():
        raise MigrationValidationError(f"{role} project path is not a directory: {project_dir}")
    try:
        resolved = project_dir.resolve(strict=True)
    except OSError as exc:
        raise MigrationValidationError(f"Cannot resolve {role.lower()} project directory: {exc}") from exc
    if resolved.parent != root:
        raise MigrationValidationError(f"{role} project directory escapes Claude projects: {project_dir}")


def validate_migration_target(target_path: str, target_encoded: str) -> None:
    _validate_encoded_path(target_path, target_encoded, "Target")
    target_dir = PROJECTS_DIR / target_encoded
    _validate_project_dir(target_dir, "Target", must_exist=False)
    if target_dir.exists():
        _reject_symlinks(target_dir, "Target project")
    recorded = _recorded_project_paths(target_encoded)
    if recorded:
        if len(recorded) != 1:
            raise MigrationValidationError(
                f"Ambiguous target path for {target_encoded}: {', '.join(sorted(recorded))}"
            )
        actual = next(iter(recorded))
        if _normalized_path(target_path) != _normalized_path(actual):
            raise MigrationValidationError(
                f"Target path mismatch for {target_encoded}: requested {target_path}, recorded {actual}"
            )
    elif target_dir.exists():
        raise MigrationValidationError(f"Cannot resolve actual target path for {target_encoded}")


def get_available_projects() -> list[tuple[str, str]]:
    """Get list of (encoded_name, actual_path) for available project dirs."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.name.startswith(".asm-migrate-"):
            continue
        if d.is_symlink():
            raise ProjectPathResolutionError(f"Claude project directory is a symlink: {d}")
        if d.is_dir():
            _validate_project_dir(d, "Source", must_exist=True)
            path = resolve_project_path(d.name)
            result.append((d.name, path))
    return result


def find_similar_dirs(target_encoded: str) -> list[str]:
    """Find directories similar to the target encoded name."""
    if not PROJECTS_DIR.exists():
        return []
    # Extract key parts for matching
    parts = set(target_encoded.strip("-").split("-"))
    results = []
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir():
            dir_parts = set(d.name.strip("-").split("-"))
            overlap = parts & dir_parts
            if len(overlap) >= len(parts) * 0.5:
                results.append(d.name)
    return results


def get_target_replacement_scope(
    target_encoded: str, target_path: str | None = None
) -> TargetReplacementScope:
    target_dir = PROJECTS_DIR / target_encoded
    if target_path is not None:
        validate_migration_target(target_path, target_encoded)
    else:
        _validate_project_dir(target_dir, "Target", must_exist=False)
    if not target_dir.exists():
        return TargetReplacementScope(0, 0, False, 0, 0)
    memory = target_dir / "memory"
    known = {"memory", "sessions-index.json"}
    return TargetReplacementScope(
        sessions=len(list(target_dir.glob("*.jsonl"))),
        memory_files=len([p for p in memory.rglob("*") if p.is_file()]) if memory.exists() else 0,
        has_index=(target_dir / "sessions-index.json").is_file(),
        other_entries=sum(
            1 for p in target_dir.iterdir()
            if p.name not in known and not (p.is_file() and p.suffix == ".jsonl")
        ),
        total_bytes=sum(p.stat().st_size for p in target_dir.rglob("*") if p.is_file()),
    )


def migrate_sessions(
    source_path: str,
    target_path: str,
    mode: str = "append",
    source_encoded: str | None = None,
    target_encoded: str | None = None,
    session_ids: list[str] | None = None,
) -> MigrateResult:
    """Migrate sessions from source project to target project.

    Args:
        source_path: Absolute path of source project (for display/path updates)
        target_path: Absolute path of target project (for display/path updates)
        mode: "append" (keep existing, skip duplicates) or "overwrite"
        source_encoded: Pre-encoded source dir name (avoids lossy re-encoding)
        target_encoded: Pre-encoded target dir name (avoids lossy re-encoding)
        session_ids: If provided, only migrate these specific session IDs.
                     If None, migrate all sessions.
    """
    if mode not in {"append", "overwrite"}:
        return MigrateResult(success=False, message=f"Unsupported migration mode: {mode}")
    if session_ids is not None and not session_ids:
        return MigrateResult(success=False, message="No session IDs selected")
    if mode == "overwrite" and session_ids is not None:
        return MigrateResult(
            success=False,
            message="Replace entire target requires the entire source project, not selected sessions",
        )

    source_encoded = source_encoded or encode_path(source_path)
    target_encoded = target_encoded or encode_path(target_path)
    source_dir = PROJECTS_DIR / source_encoded
    target_dir = PROJECTS_DIR / target_encoded

    try:
        _validate_encoded_path(source_path, source_encoded, "Source")
        _validate_encoded_path(target_path, target_encoded, "Target")
        if source_encoded == target_encoded:
            raise MigrationValidationError("Source and target are the same")
        _validate_project_dir(source_dir, "Source", must_exist=True)
        validate_migration_target(target_path, target_encoded)
        actual_source_path = resolve_project_path(source_encoded)
        if _normalized_path(source_path) != _normalized_path(actual_source_path):
            raise MigrationValidationError(
                f"Source path mismatch for {source_encoded}: requested {source_path}, "
                f"recorded {actual_source_path}"
            )
    except (MigrationValidationError, ProjectPathResolutionError, OSError) as exc:
        return MigrateResult(success=False, message=str(exc))

    all_sessions = sorted(source_dir.glob("*.jsonl"))
    if session_ids is not None:
        id_set = set(session_ids)
        found_ids = {path.stem for path in all_sessions if path.stem in id_set}
        missing_ids = sorted(id_set - found_ids)
        if missing_ids:
            return MigrateResult(
                success=False,
                message=f"Selected session IDs not found: {', '.join(missing_ids)}",
            )
        source_sessions = [path for path in all_sessions if path.stem in id_set]
    else:
        source_sessions = all_sessions
    if not source_sessions:
        return MigrateResult(success=False, message="No session files to migrate")

    try:
        with tempfile.TemporaryDirectory(prefix=".asm-migrate-", dir=PROJECTS_DIR) as temp_name:
            temp_root = Path(temp_name)
            staged_target = temp_root / "next"
            copied, skipped, memory_copied, changed, expected_sessions = _stage_migration(
                source_dir,
                target_dir,
                staged_target,
                source_sessions,
                mode,
                actual_source_path,
                target_path,
                source_encoded,
                target_encoded,
            )
            if changed:
                validate_migration_target(target_path, target_encoded)
                _commit_staged_target(staged_target, target_dir, temp_root, expected_sessions)
    except (
        MigrationValidationError,
        MigrationApplyError,
        PathRewriteError,
        OSError,
        shutil.Error,
    ) as exc:
        return MigrateResult(success=False, message=f"Migration failed: {exc}")

    msg = f"{copied} sessions migrated"
    if skipped:
        msg += f", {skipped} already in target (skipped)"
    return MigrateResult(
        success=True,
        sessions_copied=copied,
        sessions_skipped=skipped,
        memory_copied=memory_copied,
        message=f"{msg} ({actual_source_path} -> {target_path})",
    )


def _reject_symlinks(path: Path, label: str) -> None:
    if path.is_symlink():
        raise MigrationValidationError(f"{label} is a symlink: {path}")
    if path.is_dir():
        for item in path.rglob("*"):
            if item.is_symlink():
                raise MigrationValidationError(f"{label} contains a symlink: {item}")


def _copy_source_memory(source_memory: Path, target_memory: Path) -> bool:
    _reject_symlinks(source_memory, "Source memory")
    if not target_memory.exists():
        shutil.copytree(source_memory, target_memory, copy_function=shutil.copy2)
        return True
    if not target_memory.is_dir() or target_memory.is_symlink():
        raise MigrationValidationError(f"Target memory is not a regular directory: {target_memory}")
    copied = False
    for source_item in sorted(source_memory.rglob("*")):
        relative = source_item.relative_to(source_memory)
        destination = target_memory / relative
        if source_item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source_item.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_item, destination)
            copied = True
    return copied


def _stage_migration(
    source_dir: Path,
    target_dir: Path,
    staged_target: Path,
    source_sessions: list[Path],
    mode: str,
    source_path: str,
    target_path: str,
    source_encoded: str,
    target_encoded: str,
) -> tuple[int, int, bool, bool, set[str]]:
    if mode == "append" and target_dir.exists():
        _reject_symlinks(target_dir, "Target project")
        shutil.copytree(target_dir, staged_target, copy_function=shutil.copy2)
    else:
        staged_target.mkdir()

    copied = 0
    skipped = 0
    changed = mode == "overwrite"
    staged_files = []
    for source_file in source_sessions:
        if source_file.is_symlink() or not source_file.is_file():
            raise MigrationValidationError(f"Source session is not a regular file: {source_file}")
        destination = staged_target / source_file.name
        if mode == "append" and destination.exists():
            skipped += 1
            continue
        shutil.copy2(source_file, destination)
        staged_files.append(destination)
        copied += 1
        changed = True

    memory_copied = False
    source_memory = source_dir / "memory"
    if source_memory.exists():
        memory_copied = _copy_source_memory(source_memory, staged_target / "memory")
        changed = changed or memory_copied

    source_index = source_dir / "sessions-index.json"
    staged_index = None
    if source_index.exists():
        if source_index.is_symlink() or not source_index.is_file():
            raise MigrationValidationError(f"Source sessions index is not a regular file: {source_index}")
        destination = staged_target / "sessions-index.json"
        if mode == "overwrite" or not destination.exists():
            shutil.copy2(source_index, destination)
            staged_index = destination
            changed = True

    if source_path != target_path:
        _update_paths(
            staged_files,
            staged_index,
            source_path,
            target_path,
            source_encoded,
            target_encoded,
        )
    expected_sessions = {path.name for path in staged_files}
    return copied, skipped, memory_copied, changed, expected_sessions


def _commit_staged_target(
    staged_target: Path,
    target_dir: Path,
    temp_root: Path,
    expected_sessions: set[str],
) -> None:
    previous = temp_root / "previous"
    failed = temp_root / "failed"
    had_target = target_dir.exists()
    previous_moved = False
    installed = False
    try:
        _validate_project_dir(target_dir, "Target", must_exist=False)
        if had_target:
            os.replace(target_dir, previous)
            previous_moved = True
        os.replace(staged_target, target_dir)
        installed = True
        _validate_project_dir(target_dir, "Target", must_exist=True)
        for name in expected_sessions:
            installed_file = target_dir / name
            if installed_file.is_symlink() or not installed_file.is_file():
                raise MigrationApplyError(f"Installed session verification failed: {installed_file}")
        if previous_moved:
            send2trash(str(previous))
    except Exception as exc:
        rollback_errors = []
        if installed and target_dir.exists():
            try:
                os.replace(target_dir, failed)
            except OSError as rollback_exc:
                rollback_errors.append(f"cannot remove failed target: {rollback_exc}")
        if previous_moved:
            if previous.exists():
                try:
                    os.replace(previous, target_dir)
                except OSError as rollback_exc:
                    rollback_errors.append(f"cannot restore previous target: {rollback_exc}")
            else:
                rollback_errors.append("previous target is unavailable")
        if rollback_errors:
            raise MigrationApplyError(
                f"{exc}; rollback failed: {'; '.join(rollback_errors)}"
            ) from exc
        raise MigrationApplyError(str(exc)) from exc


def _replace_path_prefix(value: str, old: str, new: str) -> str:
    windows = len(old) > 1 and old[1] == ":"
    old_base = old.rstrip("/\\") or old
    compare_value = value.casefold() if windows else value
    compare_old = old_base.casefold() if windows else old_base
    if compare_value == compare_old:
        return new
    if old_base in {"/", "\\"}:
        if compare_value.startswith(compare_old):
            return new.rstrip("/\\") + old_base + value[len(old_base):]
        return value
    if not compare_value.startswith(compare_old):
        return value
    boundary = len(old_base)
    if len(value) <= boundary or value[boundary] not in "/\\":
        return value
    return new.rstrip("/\\") + value[boundary:]


def _replace_path_component(value: str, old: str, new: str) -> str:
    parts = re.split(r"([/\\])", value)
    return "".join(new if part == old else part for part in parts)


def _replace_in_obj(obj: object, old: str, new: str, restrict_keys: bool = True) -> None:
    if not isinstance(obj, dict):
        return
    allowed = _SOURCE_PATH_FIELDS if restrict_keys else _INDEX_PATH_FIELDS
    for key, value in obj.items():
        if isinstance(value, str) and key in allowed:
            obj[key] = _replace_path_prefix(value, old, new)
        elif not restrict_keys and isinstance(value, (dict, list)):
            _replace_index_paths(value, old, new)


def _replace_index_paths(obj: object, old: str, new: str) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and key in _INDEX_PATH_FIELDS:
                obj[key] = _replace_path_prefix(value, old, new)
            elif isinstance(value, (dict, list)):
                _replace_index_paths(value, old, new)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                _replace_index_paths(value, old, new)


def _replace_index_components(obj: object, old: str, new: str) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and key in _INDEX_PATH_FIELDS:
                obj[key] = _replace_path_component(value, old, new)
            elif isinstance(value, (dict, list)):
                _replace_index_components(value, old, new)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                _replace_index_components(value, old, new)


def _update_paths(
    copied_files: list[Path],
    copied_index: Path | None,
    source_path: str,
    target_path: str,
    source_encoded: str,
    target_encoded: str,
) -> None:
    """Update path references in the files copied by this run."""
    failures = []
    # Update JSONL files - parse each line as JSON to avoid partial matches
    for jsonl in copied_files:
        try:
            updated = []
            for line_number, line in enumerate(jsonl.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise PathRewriteError(f"line {line_number}: {exc.msg}") from exc
                _replace_in_obj(obj, source_path, target_path, restrict_keys=True)
                updated.append(json.dumps(obj, ensure_ascii=False))
            jsonl.write_text("\n".join(updated) + ("\n" if updated else ""))
        except (OSError, PathRewriteError) as exc:
            failures.append(f"{jsonl.name}: {exc}")

    # sessions-index.json - parse as JSON, not string replace
    if copied_index is not None:
        try:
            data = json.loads(copied_index.read_text())
            _replace_in_obj(data, source_path, target_path, restrict_keys=False)
            _replace_index_components(data, source_encoded, target_encoded)
            copied_index.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"sessions-index.json: {exc}")

    if failures:
        raise PathRewriteError("path rewrite failed for " + "; ".join(failures))
