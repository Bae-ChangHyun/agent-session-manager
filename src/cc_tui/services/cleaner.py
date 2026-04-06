"""Service for cleaning (trashing) Claude Code data."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from cc_tui.models import CLAUDE_DIR, DEBUG_DIR, FILE_HISTORY_DIR, PROJECTS_DIR, SESSION_ENV_DIR, TODOS_DIR
from cc_tui.services.recovery import create_recovery_snapshot

logger = logging.getLogger(__name__)

# --- Path traversal prevention ---

_ALLOWED_ROOTS = (CLAUDE_DIR,)


def _validate_path(path: Path) -> Path:
    """Validate path and return resolved version. Raises ValueError if invalid."""
    if path.is_symlink():
        raise ValueError(f"Refusing to operate on symlink: {path}")
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in _ALLOWED_ROOTS):
        raise ValueError(f"Path outside allowed directories: {path}")
    return resolved


# --- Trash logging (recovery mechanism) ---

_TRASH_LOG = Path.home() / ".cc-tui" / "trash-log.jsonl"
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
    target = PROJECTS_DIR / dir_name
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        create_recovery_snapshot(resolved, "session")
        _trash_related_session_envs(dir_name)
        _log_trash(resolved, "session")
        send2trash(str(resolved))
        return True
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


def _trash_related_session_envs(dir_name: str) -> None:
    """Trash session-env directories related to a project dir."""
    if not SESSION_ENV_DIR.exists():
        return
    try:
        for d in SESSION_ENV_DIR.iterdir():
            if d.is_dir() and (d.name == dir_name or d.name.startswith(dir_name + "-")):
                try:
                    resolved_d = _validate_path(d)
                    create_recovery_snapshot(resolved_d, "session-env")
                    _log_trash(resolved_d, "session-env")
                    send2trash(str(resolved_d))
                except (ValueError, PermissionError, OSError) as e:
                    logger.warning("Failed to trash session-env %s: %s", d.name, e)
    except (PermissionError, OSError):
        pass


def trash_single_session_file(project_encoded: str, session_id: str) -> bool:
    """Move a single .jsonl session file to trash."""
    target = PROJECTS_DIR / project_encoded / f"{session_id}.jsonl"
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        create_recovery_snapshot(resolved, "session")
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
        create_recovery_snapshot(resolved, "file_history")
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
        create_recovery_snapshot(resolved, "debug")
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
    """Move a todo file to trash."""
    target = TODOS_DIR / name
    if not target.exists():
        return False
    try:
        resolved = _validate_path(target)
        create_recovery_snapshot(resolved, "todo")
        _log_trash(resolved, "todo")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash todo file %s: %s", name, e)
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
    """Find and trash empty todo files ([], {}, or empty content)."""
    return _prune_empty_in_dir(TODOS_DIR, "todo")


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
                create_recovery_snapshot(resolved_f, category)
                _log_trash(resolved_f, category)
                send2trash(str(resolved_f))
                ok += 1
        except (ValueError, PermissionError, OSError) as e:
            logger.warning("Failed to prune %s: %s", f.name, e)
            fail += 1
    return ok, fail


def count_empty_files(directory: Path) -> int:
    """Count files with empty content ([], {}, or empty)."""
    if not directory.exists():
        return 0
    count = 0
    try:
        for f in directory.iterdir():
            if not f.is_file():
                continue
            try:
                content = f.read_text(errors="replace").strip()
                if content in ("[]", "{}", ""):
                    count += 1
            except OSError:
                pass
    except (PermissionError, OSError):
        pass
    return count


def trash_path(path: str | Path) -> bool:
    """Generic: move any path to trash."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        resolved = _validate_path(p)
        create_recovery_snapshot(resolved, "generic")
        _log_trash(resolved, "generic")
        send2trash(str(resolved))
        return True
    except (ValueError, PermissionError, OSError) as e:
        logger.warning("Failed to trash path %s: %s", path, e)
        return False
