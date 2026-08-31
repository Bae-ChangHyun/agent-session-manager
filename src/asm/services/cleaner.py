"""Service for cleaning (trashing) Claude Code data."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from asm.models import CLAUDE_DIR, DEBUG_DIR, FILE_HISTORY_DIR, PROJECTS_DIR, SESSION_ENV_DIR, TASKS_DIR, TODOS_DIR
from asm.services.recovery import create_recovery_snapshot, create_recovery_snapshots

logger = logging.getLogger(__name__)

# --- Path traversal prevention ---

_ALLOWED_ROOTS = (CLAUDE_DIR,)
_SAFE_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z|-[A-Za-z0-9._-]*\Z")


def _validate_path(path: Path) -> Path:
    """Validate path and return resolved version. Raises ValueError if invalid."""
    if path.is_symlink():
        raise ValueError(f"Refusing to operate on symlink: {path}")
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in _ALLOWED_ROOTS):
        raise ValueError(f"Path outside allowed directories: {path}")
    return resolved


def _validate_component(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT_RE.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _create_required_snapshot(path: Path, category: str) -> str:
    snapshot_id = create_recovery_snapshot(path, category)
    if not isinstance(snapshot_id, str) or not _SAFE_COMPONENT_RE.fullmatch(snapshot_id):
        raise OSError(f"Recovery snapshot failed for {path}")
    return snapshot_id


def _create_required_snapshots(items: list[tuple[Path, str]]) -> list[str]:
    snapshot_ids = create_recovery_snapshots(items)
    if not isinstance(snapshot_ids, list) or len(snapshot_ids) != len(items):
        raise OSError("Recovery snapshot batch failed")
    if any(not isinstance(item, str) or not _SAFE_COMPONENT_RE.fullmatch(item) for item in snapshot_ids):
        raise OSError("Recovery snapshot batch returned invalid ids")
    return snapshot_ids


# --- Trash logging (recovery mechanism) ---

_TRASH_LOG = Path.home() / ".asm" / "trash-log.jsonl"
_log_lock = threading.Lock()


def _log_trash(path: Path, category: str) -> None:
    """Append a record to the trash log (thread-safe)."""
    _TRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "path": str(path),
        "category": category,
    }
    with _log_lock:
        with open(_TRASH_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")


# --- Trash functions ---


def trash_session(dir_name: str) -> bool:
    """Move a session directory to trash, including related session-env dirs."""
    try:
        _validate_component(dir_name, "project directory")
        target = PROJECTS_DIR / dir_name
        if not target.exists():
            return False
        resolved = _validate_path(target)
        related = _related_session_envs(dir_name)
        snapshot_items = [(resolved, "session")]
        snapshot_items.extend((env_path, "session-env") for env_path in related)
        _create_required_snapshots(snapshot_items)
        _log_trash(resolved, "session")
        send2trash(str(resolved))
        failed = False
        for env_path in related:
            try:
                _log_trash(env_path, "session-env")
                send2trash(str(env_path))
            except (ValueError, PermissionError, OSError) as exc:
                logger.warning("Failed to trash session-env %s: %s", env_path.name, exc)
                failed = True
        return not failed
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash session %s: %s", dir_name, e)
        return False


def trash_sessions(dir_names: list[str]) -> tuple[int, int]:
    """Trash multiple sessions. Returns (success_count, fail_count)."""
    ok, fail = 0, 0
    for name in dir_names:
        if trash_session(name):
            ok += 1
        else:
            fail += 1
    return ok, fail


def _related_session_envs(dir_name: str) -> list[Path]:
    if not SESSION_ENV_DIR.exists():
        return []
    related = []
    for d in SESSION_ENV_DIR.iterdir():
        if d.is_dir() and (d.name == dir_name or d.name.startswith(dir_name + "-")):
            related.append(_validate_path(d))
    return related


def trash_single_session_file(project_encoded: str, session_id: str) -> bool:
    """Move a single .jsonl session file to trash."""
    try:
        _validate_component(project_encoded, "project directory")
        _validate_component(session_id, "session id")
        project_dir = PROJECTS_DIR / project_encoded
        target = project_dir / f"{session_id}.jsonl"
        if not target.exists():
            return False
        resolved_project = _validate_path(project_dir)
        resolved = _validate_path(target)
        if resolved.parent != resolved_project:
            raise ValueError(f"Session file outside project directory: {target}")
        _create_required_snapshot(resolved, "session")
        _log_trash(resolved, "session")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash session file %s: %s", session_id, e)
        return False


def trash_file_history(dir_name: str) -> bool:
    """Move a file history directory to trash."""
    target = FILE_HISTORY_DIR / dir_name
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        _create_required_snapshot(resolved, "file_history")
        _log_trash(resolved, "file_history")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash file history %s: %s", dir_name, e)
        return False


def trash_file_histories(dir_names: list[str]) -> tuple[int, int]:
    """Trash multiple file history entries."""
    ok, fail = 0, 0
    for name in dir_names:
        if trash_file_history(name):
            ok += 1
        else:
            fail += 1
    return ok, fail


def trash_debug_file(name: str) -> bool:
    """Move a debug file to trash."""
    target = DEBUG_DIR / name
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        _create_required_snapshot(resolved, "debug")
        _log_trash(resolved, "debug")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash debug file %s: %s", name, e)
        return False


def trash_debug_files(names: list[str]) -> tuple[int, int]:
    """Trash multiple debug files."""
    ok, fail = 0, 0
    for name in names:
        if trash_debug_file(name):
            ok += 1
        else:
            fail += 1
    return ok, fail


def trash_todo_file(name: str) -> bool:
    """Move a todo/task entry to trash.

    ``name`` is a session id (a ``tasks/<sessionId>/`` directory) on Claude Code
    >= 2.1, or a legacy ``todos/*.json`` filename on older versions.
    """
    target = TASKS_DIR / name
    if not target.exists():
        target = TODOS_DIR / name
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        _create_required_snapshot(resolved, "todo")
        _log_trash(resolved, "todo")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash todo entry %s: %s", name, e)
        return False


def trash_todo_files(names: list[str]) -> tuple[int, int]:
    """Trash multiple todo files."""
    ok, fail = 0, 0
    for name in names:
        if trash_todo_file(name):
            ok += 1
        else:
            fail += 1
    return ok, fail


def prune_empty_debug_files() -> tuple[int, int]:
    """Find and trash empty debug files ([], {}, or empty content)."""
    return _prune_empty_in_dir(DEBUG_DIR, "debug")


def prune_empty_todo_files() -> tuple[int, int]:
    """Find and trash empty todo/task entries.

    On Claude Code >= 2.1 this trashes ``tasks/<sessionId>/`` directories that
    hold no task json files (only lock/highwatermark housekeeping files). On
    older versions it trashes empty ``todos/*.json`` files.
    """
    if TASKS_DIR.exists():
        return _prune_empty_task_dirs()
    return _prune_empty_in_dir(TODOS_DIR, "todo")


def _task_dir_is_empty(d: Path) -> bool:
    """A task dir is empty if it has no task json files (locks don't count)."""
    try:
        return not any(f.suffix == ".json" for f in d.iterdir() if f.is_file())
    except (PermissionError, OSError):
        return False


def _prune_empty_task_dirs() -> tuple[int, int]:
    """Trash tasks/<sessionId>/ directories that contain no task json files."""
    if not TASKS_DIR.exists():
        return 0, 0
    ok, fail = 0, 0
    for d in TASKS_DIR.iterdir():
        if not d.is_dir() or not _task_dir_is_empty(d):
            continue
        try:
            resolved = _validate_path(d)
            _create_required_snapshot(resolved, "todo")
            _log_trash(resolved, "todo")
            send2trash(str(resolved))
            ok += 1
        except (ValueError, PermissionError, OSError) as e:
            logger.warning("Failed to prune empty task dir %s: %s", d.name, e)
            fail += 1
    return ok, fail


def count_empty_todos() -> int:
    """Count empty todo/task entries (task dirs with no json, or empty legacy files)."""
    if TASKS_DIR.exists():
        try:
            return sum(1 for d in TASKS_DIR.iterdir() if d.is_dir() and _task_dir_is_empty(d))
        except (PermissionError, OSError):
            return 0
    return count_empty_files(TODOS_DIR)


def _prune_empty_in_dir(directory: Path, category: str = "generic") -> tuple[int, int]:
    """Trash files whose content is [], {}, or empty."""
    if not directory.exists():
        return 0, 0
    ok, fail = 0, 0
    for f in directory.iterdir():
        if not f.is_file():
            continue
        try:
            content = f.read_text(errors="replace").strip()
            if content in ("[]", "{}", ""):
                resolved_f = _validate_path(f)
                _create_required_snapshot(resolved_f, category)
                _log_trash(resolved_f, category)
                send2trash(str(resolved_f))
                ok += 1
        except (ValueError, PermissionError, OSError) as e:
            logger.warning("Failed to prune %s: %s", f.name, e)
            fail += 1
    return ok, fail


def count_empty_files(directory: Path) -> int:
    """Count files with empty content ([], {}, or empty)."""
    return len(_list_empty_files(directory))


def _list_empty_files(directory: Path) -> list[str]:
    """Names of files whose content is [], {}, or empty."""
    if not directory.exists():
        return []
    names: list[str] = []
    try:
        for f in sorted(directory.iterdir()):
            if not f.is_file():
                continue
            try:
                content = f.read_text(errors="replace").strip()
                if content in ("[]", "{}", ""):
                    names.append(f.name)
            except OSError:
                pass
    except (PermissionError, OSError):
        pass
    return names


def list_empty_debug_files() -> list[str]:
    """Names of empty debug files (what prune_empty_debug_files would trash)."""
    return _list_empty_files(DEBUG_DIR)


def list_empty_todo_entries() -> list[str]:
    """Names of empty todo/task entries (what prune_empty_todo_files would trash)."""
    if TASKS_DIR.exists():
        try:
            return sorted(d.name for d in TASKS_DIR.iterdir() if d.is_dir() and _task_dir_is_empty(d))
        except (PermissionError, OSError):
            return []
    return _list_empty_files(TODOS_DIR)


def trash_codex_session(path: str | Path) -> bool:
    """Move a Codex rollout session file to trash (validated under a Codex home)."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        if p.is_symlink():
            raise ValueError(f"Refusing to operate on symlink: {p}")
        resolved = p.resolve()
        from asm.services import codex_data

        # Deletable range must equal the scanned range, or a session listed from
        # a second account home could not be trashed.
        roots = [d.resolve() for d in codex_data._session_dirs() if d.exists()]
        if not any(resolved.is_relative_to(root) for root in roots):
            raise ValueError(f"Path outside Codex dir: {p}")
        _create_required_snapshot(resolved, "codex-session")
        _log_trash(resolved, "codex-session")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash codex session %s: %s", path, e)
        return False
