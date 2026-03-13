"""Data models for CC-TUI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def encode_path(path: str) -> str:
    """Encode a filesystem path to Claude's directory name format.

    Note: This encoding is lossy -- different paths may produce the same encoded
    name (e.g., /home/user/my-project and /home/user/my_project both become
    -home-user-my-project). This matches Claude Code's own encoding scheme.
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def decode_path_hint(encoded: str) -> str:
    """Best-effort decode of an encoded path (lossy, for display only)."""
    parts = encoded.strip("-").split("-")
    return "/" + "/".join(p for p in parts if p)


CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"
PROJECTS_DIR = CLAUDE_DIR / "projects"
SESSION_ENV_DIR = CLAUDE_DIR / "session-env"
FILE_HISTORY_DIR = CLAUDE_DIR / "file-history"
DEBUG_DIR = CLAUDE_DIR / "debug"
TODOS_DIR = CLAUDE_DIR / "todos"
BACKUP_BASE_DIR = Path.home() / ".cc-tui" / "backups"


@dataclass
class ProjectInfo:
    """A project registered in .claude.json."""

    path: str
    exists: bool = False
    last_cost: float | None = None
    last_duration: float | None = None
    session_env_dirs: list[str] = field(default_factory=list)


@dataclass
class SessionInfo:
    """A session data directory under ~/.claude/projects/."""

    dir_name: str
    actual_path: str
    size_bytes: int = 0
    file_count: int = 0
    session_env_dirs: list[str] = field(default_factory=list)
    is_orphaned: bool = False


@dataclass
class SessionDetail:
    """Detailed session info from SDK or JSONL parsing."""

    session_id: str
    summary: str = ""
    last_modified: float = 0
    file_size: int = 0
    first_prompt: str = ""
    git_branch: str = ""
    cwd: str = ""
    project_dir: str = ""


@dataclass
class FileHistoryEntry:
    """A file history entry."""

    dir_name: str
    path: str
    size_bytes: int = 0
    is_orphaned: bool = False


@dataclass
class DebugEntry:
    """A debug file entry."""

    name: str
    path: str
    size_bytes: int = 0
    is_orphaned: bool = False


@dataclass
class TodoEntry:
    """A todo file entry."""

    name: str
    path: str
    size_bytes: int = 0
    is_orphaned: bool = False


@dataclass
class BackupInfo:
    """A backup entry."""

    name: str
    path: str
    created: float = 0
    size_bytes: int = 0


@dataclass
class Stats:
    """Overall statistics."""

    total_projects: int = 0
    total_sessions: int = 0
    total_file_history: int = 0
    total_debug: int = 0
    total_todos: int = 0
    orphaned_sessions: int = 0
    orphaned_file_history: int = 0
    orphaned_debug: int = 0
    orphaned_todos: int = 0
    claude_dir_size: int = 0
    projects_dir_size: int = 0
