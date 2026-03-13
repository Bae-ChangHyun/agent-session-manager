"""Service for cleaning (trashing) Claude Code data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from cc_tui.models import CLAUDE_DIR, DEBUG_DIR, FILE_HISTORY_DIR, PROJECTS_DIR, SESSION_ENV_DIR, TODOS_DIR

# --- Path traversal prevention ---

_ALLOWED_ROOTS = (CLAUDE_DIR,)


def _validate_path(path: Path) -> None:
    """Raise ValueError if path is outside allowed directories."""
    resolved = path.resolve()
    if not any(
        resolved == root.resolve() or str(resolved).startswith(str(root.resolve()) + "/")
        for root in _ALLOWED_ROOTS
    ):
        raise ValueError(f"Path outside allowed directories: {path}")


# --- Trash logging (recovery mechanism) ---

_TRASH_LOG = Path.home() / ".cc-tui" / "trash-log.jsonl"


def _log_trash(path: Path, category: str) -> None:
    """Append a record to the trash log."""
    _TRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "path": str(path),
        "category": category,
    }
    with open(_TRASH_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Trash functions ---


def trash_session(dir_name: str) -> bool:
    """Move a session directory to trash, including related session-env dirs."""
    target = PROJECTS_DIR / dir_name
    if not target.exists():
        return False
    try:
        _validate_path(target)
        # Also trash related session-env dirs
        _trash_related_session_envs(dir_name)
        _log_trash(target, "session")
        send2trash(str(target))
        return True
    except Exception:
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
                _validate_path(d)
                _log_trash(d, "session")
                send2trash(str(d))
    except (PermissionError, OSError, ValueError):
        pass


def trash_single_session_file(project_encoded: str, session_id: str) -> bool:
    """Move a single .jsonl session file to trash."""
    target = PROJECTS_DIR / project_encoded / f"{session_id}.jsonl"
    if not target.exists():
        return False
    try:
        _validate_path(target)
        _log_trash(target, "session")
        send2trash(str(target))
        return True
    except Exception:
        return False


def trash_file_history(dir_name: str) -> bool:
    """Move a file history directory to trash."""
    target = FILE_HISTORY_DIR / dir_name
    if not target.exists():
        return False
    try:
        _validate_path(target)
        _log_trash(target, "file_history")
        send2trash(str(target))
        return True
    except Exception:
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
        _validate_path(target)
        _log_trash(target, "debug")
        send2trash(str(target))
        return True
    except Exception:
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
        _validate_path(target)
        _log_trash(target, "todo")
        send2trash(str(target))
        return True
    except Exception:
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
                _validate_path(f)
                _log_trash(f, category)
                send2trash(str(f))
                ok += 1
        except Exception:
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
        _validate_path(p)
        _log_trash(p, "generic")
        send2trash(str(p))
        return True
    except Exception:
        return False
