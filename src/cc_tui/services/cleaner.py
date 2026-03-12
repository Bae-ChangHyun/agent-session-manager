"""Service for cleaning (trashing) Claude Code data."""

from __future__ import annotations

from pathlib import Path

from send2trash import send2trash

from cc_tui.models import DEBUG_DIR, FILE_HISTORY_DIR, PROJECTS_DIR, SESSION_ENV_DIR, TODOS_DIR


def trash_session(dir_name: str) -> bool:
    """Move a session directory to trash, including related session-env dirs."""
    target = PROJECTS_DIR / dir_name
    if not target.exists():
        return False
    try:
        # Also trash related session-env dirs
        _trash_related_session_envs(dir_name)
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
            if d.is_dir() and dir_name in d.name:
                send2trash(str(d))
    except (PermissionError, OSError):
        pass


def trash_file_history(dir_name: str) -> bool:
    """Move a file history directory to trash."""
    target = FILE_HISTORY_DIR / dir_name
    if not target.exists():
        return False
    try:
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


def trash_path(path: str | Path) -> bool:
    """Generic: move any path to trash."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        send2trash(str(p))
        return True
    except Exception:
        return False
