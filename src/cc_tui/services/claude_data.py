"""Service for reading Claude Code data from filesystem and SDK."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cc_tui.models import (
    CLAUDE_DIR,
    CLAUDE_JSON,
    DEBUG_DIR,
    FILE_HISTORY_DIR,
    PROJECTS_DIR,
    SESSION_ENV_DIR,
    TODOS_DIR,
    DebugEntry,
    FileHistoryEntry,
    ProjectInfo,
    SessionDetail,
    SessionInfo,
    Stats,
    TodoEntry,
    encode_path,
)


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except (PermissionError, OSError):
        pass
    return total


def _file_count(path: Path) -> int:
    """Count files and directories in a path."""
    try:
        return sum(1 for _ in path.iterdir())
    except (PermissionError, OSError):
        return 0


def _get_session_envs(project_path: str) -> list[str]:
    """Find session-env directories associated with a project path."""
    encoded = encode_path(project_path)
    envs = []
    if SESSION_ENV_DIR.exists():
        try:
            for d in SESSION_ENV_DIR.iterdir():
                if d.is_dir() and encoded in d.name:
                    envs.append(d.name)
        except (PermissionError, OSError):
            pass
    return envs


def load_claude_json() -> dict:
    """Load and parse .claude.json."""
    if not CLAUDE_JSON.exists():
        return {}
    try:
        return json.loads(CLAUDE_JSON.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_projects() -> list[ProjectInfo]:
    """Get all projects from .claude.json."""
    data = load_claude_json()
    projects_data = data.get("projects", {})
    result = []
    for path_str, config in projects_data.items():
        exists = Path(path_str).exists()
        result.append(
            ProjectInfo(
                path=path_str,
                exists=exists,
                last_cost=config.get("lastCost"),
                last_duration=config.get("lastDuration"),
                session_env_dirs=_get_session_envs(path_str),
            )
        )
    return result


def get_project_paths() -> set[str]:
    """Get set of all project paths from .claude.json."""
    data = load_claude_json()
    return set(data.get("projects", {}).keys())


def get_sessions() -> list[SessionInfo]:
    """Get all session data directories."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    project_paths = get_project_paths()
    try:
        for d in sorted(PROJECTS_DIR.iterdir()):
            if not d.is_dir():
                continue
            actual_path = d.name
            # Check if this session dir corresponds to any project
            is_orphaned = True
            for pp in project_paths:
                if encode_path(pp) == actual_path:
                    is_orphaned = False
                    break

            result.append(
                SessionInfo(
                    dir_name=d.name,
                    actual_path=str(d),
                    size_bytes=_dir_size(d),
                    file_count=_file_count(d),
                    session_env_dirs=_find_session_envs_for_dir(d.name),
                    is_orphaned=is_orphaned,
                )
            )
    except (PermissionError, OSError):
        pass
    return result


def _find_session_envs_for_dir(dir_name: str) -> list[str]:
    """Find session-env dirs matching a project dir name."""
    envs = []
    if SESSION_ENV_DIR.exists():
        try:
            for d in SESSION_ENV_DIR.iterdir():
                if d.is_dir() and dir_name in d.name:
                    envs.append(d.name)
        except (PermissionError, OSError):
            pass
    return envs


def get_session_details(project_dir: str | None = None) -> list[SessionDetail]:
    """Get detailed session info using SDK if available, fallback to JSONL parsing."""
    try:
        return _get_sessions_via_sdk(project_dir)
    except Exception:
        return _get_sessions_via_jsonl(project_dir)


def _get_sessions_via_sdk(project_dir: str | None) -> list[SessionDetail]:
    """Use claude-agent-sdk to list sessions."""
    from claude_agent_sdk import list_sessions

    sessions = list_sessions(directory=project_dir, limit=100)
    result = []
    for s in sessions:
        result.append(
            SessionDetail(
                session_id=s.session_id,
                summary=s.summary or "",
                last_modified=s.last_modified or 0,
                file_size=s.file_size or 0,
                first_prompt=s.first_prompt or "",
                git_branch=s.git_branch or "",
                cwd=s.cwd or "",
                project_dir=project_dir or "",
            )
        )
    return result


def _get_sessions_via_jsonl(project_dir: str | None) -> list[SessionDetail]:
    """Fallback: parse JSONL session files directly."""
    search_dirs = []
    if project_dir:
        encoded = encode_path(project_dir)
        p = PROJECTS_DIR / encoded
        if p.exists():
            search_dirs.append(p)
    else:
        if PROJECTS_DIR.exists():
            search_dirs = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]

    result = []
    for d in search_dirs:
        for jsonl in d.glob("*.jsonl"):
            try:
                stat = jsonl.stat()
                first_prompt = ""
                session_id = jsonl.stem
                # Read first user message for summary
                with open(jsonl) as f:
                    for line in f:
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "user":
                                content = msg.get("message", {}).get("content", "")
                                if isinstance(content, str):
                                    first_prompt = content[:100]
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            first_prompt = block.get("text", "")[:100]
                                            break
                                break
                        except json.JSONDecodeError:
                            continue
                result.append(
                    SessionDetail(
                        session_id=session_id,
                        summary=first_prompt,
                        last_modified=stat.st_mtime,
                        file_size=stat.st_size,
                        first_prompt=first_prompt,
                        cwd="",
                        project_dir=d.name,
                    )
                )
            except (OSError, json.JSONDecodeError):
                continue
    result.sort(key=lambda s: s.last_modified, reverse=True)
    return result


def get_session_messages(session_id: str, project_dir: str | None = None, limit: int = 50) -> list[dict]:
    """Get messages from a session. Uses SDK if available, fallback to JSONL."""
    try:
        return _get_messages_via_sdk(session_id, project_dir, limit)
    except Exception:
        return _get_messages_via_jsonl(session_id, project_dir, limit)


def _get_messages_via_sdk(session_id: str, project_dir: str | None, limit: int) -> list[dict]:
    """Use SDK to get session messages."""
    from claude_agent_sdk import get_session_messages as sdk_get_messages

    messages = sdk_get_messages(session_id=session_id, directory=project_dir, limit=limit)
    return [
        {
            "type": m.type,
            "content": _extract_text_content(m.message) if hasattr(m, "message") else str(m),
        }
        for m in messages
    ]


def _get_messages_via_jsonl(session_id: str, project_dir: str | None, limit: int) -> list[dict]:
    """Fallback: parse JSONL directly."""
    # Find the JSONL file
    jsonl_path = None
    if project_dir:
        encoded = encode_path(project_dir)
        candidate = PROJECTS_DIR / encoded / f"{session_id}.jsonl"
        if candidate.exists():
            jsonl_path = candidate
    else:
        if PROJECTS_DIR.exists():
            for d in PROJECTS_DIR.iterdir():
                candidate = d / f"{session_id}.jsonl"
                if candidate.exists():
                    jsonl_path = candidate
                    break

    if not jsonl_path:
        return []

    messages = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    msg_type = msg.get("type")
                    if msg_type in ("user", "assistant"):
                        content = _extract_text_content(msg.get("message", {}))
                        if content:
                            messages.append({"type": msg_type, "content": content})
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    return messages[-limit:] if len(messages) > limit else messages


def _extract_text_content(message: dict | str) -> str:
    """Extract text content from a message object."""
    if isinstance(message, str):
        return message
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    texts.append(f"[Tool: {block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    texts.append("[Tool Result]")
        return "\n".join(texts)
    return str(content)


def get_file_history() -> list[FileHistoryEntry]:
    """Get file history entries."""
    if not FILE_HISTORY_DIR.exists():
        return []
    project_paths = get_project_paths()
    encoded_paths = {encode_path(p) for p in project_paths}
    result = []
    try:
        for d in sorted(FILE_HISTORY_DIR.iterdir()):
            if not d.is_dir():
                continue
            is_orphaned = d.name not in encoded_paths
            result.append(
                FileHistoryEntry(
                    dir_name=d.name,
                    path=str(d),
                    size_bytes=_dir_size(d),
                    is_orphaned=is_orphaned,
                )
            )
    except (PermissionError, OSError):
        pass
    return result


def get_debug_files() -> list[DebugEntry]:
    """Get debug file entries."""
    if not DEBUG_DIR.exists():
        return []
    result = []
    try:
        for f in sorted(DEBUG_DIR.iterdir()):
            size = f.stat().st_size if f.is_file() else _dir_size(f)
            result.append(
                DebugEntry(name=f.name, path=str(f), size_bytes=size)
            )
    except (PermissionError, OSError):
        pass
    return result


def get_todos() -> list[TodoEntry]:
    """Get todo file entries."""
    if not TODOS_DIR.exists():
        return []
    result = []
    try:
        for f in sorted(TODOS_DIR.iterdir()):
            size = f.stat().st_size if f.is_file() else _dir_size(f)
            result.append(
                TodoEntry(name=f.name, path=str(f), size_bytes=size)
            )
    except (PermissionError, OSError):
        pass
    return result


def get_stats() -> Stats:
    """Calculate overall statistics."""
    projects = get_projects()
    sessions = get_sessions()
    file_history = get_file_history()
    debug_files = get_debug_files()
    todos = get_todos()

    return Stats(
        total_projects=len(projects),
        total_sessions=len(sessions),
        total_file_history=len(file_history),
        total_debug=len(debug_files),
        total_todos=len(todos),
        orphaned_sessions=sum(1 for s in sessions if s.is_orphaned),
        orphaned_file_history=sum(1 for f in file_history if f.is_orphaned),
        claude_dir_size=_dir_size(CLAUDE_DIR) if CLAUDE_DIR.exists() else 0,
        projects_dir_size=_dir_size(PROJECTS_DIR) if PROJECTS_DIR.exists() else 0,
    )


def remove_project_from_json(project_path: str) -> bool:
    """Remove a project entry from .claude.json."""
    data = load_claude_json()
    projects = data.get("projects", {})
    if project_path in projects:
        del projects[project_path]
        data["projects"] = projects
        try:
            CLAUDE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        except OSError:
            return False
    return False
