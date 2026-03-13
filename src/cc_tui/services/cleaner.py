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


def trash_single_session_file(project_encoded: str, session_id: str) -> bool:
    """Move a single .jsonl session file to trash."""
    target = PROJECTS_DIR / project_encoded / f"{session_id}.jsonl"
    if not target.exists():
        return False
    try:
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


def prune_empty_debug_files() -> tuple[int, int]:
    """Find and trash empty debug files ([], {}, or empty content)."""
    return _prune_empty_in_dir(DEBUG_DIR)


def prune_empty_todo_files() -> tuple[int, int]:
    """Find and trash empty todo files ([], {}, or empty content)."""
    return _prune_empty_in_dir(TODOS_DIR)


def _prune_empty_in_dir(directory: Path) -> tuple[int, int]:
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
        send2trash(str(p))
        return True
    except Exception:
        return False
