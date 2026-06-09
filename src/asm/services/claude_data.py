"""Service for reading Claude Code data from filesystem and SDK."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

_SDK_FALLBACK_EXCEPTIONS = (
    ImportError,
    ModuleNotFoundError,
    OSError,
    ValueError,
    TypeError,
    AttributeError,
)


from asm.models import (
    CLAUDE_DIR,
    CLAUDE_JSON,
    DEBUG_DIR,
    FILE_HISTORY_DIR,
    PROJECTS_DIR,
    SESSION_ENV_DIR,
    TASKS_DIR,
    TODOS_DIR,
    DebugEntry,
    FileHistoryEntry,
    ProjectInfo,
    SessionDetail,
    SessionInfo,
    Stats,
    TodoEntry,
    decode_path_hint,
    encode_path,
)


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory.

    Uses ``du -sb`` on Linux for speed, falls back to pure-Python walk
    on Windows / macOS / when the command fails.
    """
    if sys.platform != "win32":
        import subprocess
        try:
            result = subprocess.run(
                ["du", "-sb", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0])
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
            pass
    # Pure-Python fallback (Windows, macOS, or du failure)
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


def _build_encoded_to_paths_map() -> dict[str, list[str]]:
    """Build encoded project-dir name -> project paths mapping."""
    encoded_to_paths: dict[str, list[str]] = defaultdict(list)
    for path_str in sorted(get_project_paths()):
        encoded_to_paths[encode_path(path_str)].append(path_str)
    return dict(encoded_to_paths)


def _resolve_project_dir(project_ref: str | None) -> Path | None:
    """Resolve a project path or already-encoded directory name to a projects dir.

    ``project_ref`` may be either an absolute project path (from .claude.json) or
    an already-encoded directory name (e.g. ``-home-bch-foo``). Note that
    ``PROJECTS_DIR / "/abs/path"`` collapses to ``/abs/path`` in pathlib (an
    absolute right-hand operand discards the left), so we must encode an absolute
    path *before* joining — otherwise it resolves to the real project source dir,
    which has no session files.
    """
    if not project_ref:
        return None
    # Already-encoded directory name (relative, no leading slash).
    if not project_ref.startswith("/"):
        direct = PROJECTS_DIR / project_ref
        if direct.exists() and direct.parent == PROJECTS_DIR:
            return direct
    encoded = encode_path(project_ref)
    candidate = PROJECTS_DIR / encoded
    if candidate.exists():
        return candidate
    return None


def _project_label_for_dir(dir_name: str, encoded_to_paths: dict[str, list[str]]) -> str:
    """Return a readable project label for a Claude projects dir."""
    matches = encoded_to_paths.get(dir_name, [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return f"[ambiguous] {' | '.join(matches)}"
    return decode_path_hint(dir_name)


def get_sessions() -> list[SessionInfo]:
    """Get all session data directories."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    encoded_to_paths = _build_encoded_to_paths_map()
    try:
        for d in sorted(PROJECTS_DIR.iterdir()):
            if not d.is_dir():
                continue
            actual_path = d.name
            is_orphaned = actual_path not in encoded_to_paths

            result.append(
                SessionInfo(
                    dir_name=d.name,
                    actual_path=str(d),
                    size_bytes=0,  # Calculated lazily in UI
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
                if d.is_dir() and (d.name == dir_name or d.name.startswith(dir_name + "-")):
                    envs.append(d.name)
        except (PermissionError, OSError):
            pass
    return envs


def get_session_details(project_dir: str | None = None) -> list[SessionDetail]:
    """Get detailed session info using SDK if available, fallback to JSONL parsing."""
    try:
        return _get_sessions_via_sdk(project_dir)
    except _SDK_FALLBACK_EXCEPTIONS:
        logger.debug("SDK path failed for get_session_details, falling back to JSONL", exc_info=True)
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
        p = _resolve_project_dir(project_dir)
        if p and p.exists():
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
    if project_dir and _resolve_project_dir(project_dir):
        return _get_messages_via_jsonl(session_id, project_dir, limit)
    try:
        return _get_messages_via_sdk(session_id, project_dir, limit)
    except _SDK_FALLBACK_EXCEPTIONS:
        logger.debug("SDK path failed for get_session_messages, falling back to JSONL", exc_info=True)
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
        project_root = _resolve_project_dir(project_dir)
        candidate = project_root / f"{session_id}.jsonl" if project_root else None
        if candidate and candidate.exists():
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
    ai_title = ""
    meta_lines: list[str] = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("type")
                if msg_type in ("user", "assistant"):
                    content = _extract_text_content(msg.get("message", {}))
                    if content:
                        messages.append({"type": msg_type, "content": content})
                elif msg_type == "ai-title":
                    ai_title = msg.get("aiTitle", "") or ai_title
                elif msg_type == "pr-link":
                    url = msg.get("url") or msg.get("prLink") or ""
                    if url:
                        meta_lines.append(f"PR: {url}")
    except OSError:
        pass

    if messages:
        return messages[-limit:] if len(messages) > limit else messages

    # No conversation turns — surface whatever metadata exists so the preview is
    # informative instead of blank (these are title/PR/automation-only sessions).
    if ai_title or meta_lines:
        info = "[no conversation — metadata only]"
        if ai_title:
            info += f"\n\nTitle: {ai_title}"
        if meta_lines:
            info += "\n" + "\n".join(meta_lines)
        return [{"type": "meta", "content": info}]
    return []


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
    active_session_ids = _get_active_session_ids()
    result = []
    try:
        for d in sorted(FILE_HISTORY_DIR.iterdir()):
            if not d.is_dir():
                continue
            is_orphaned = d.name not in active_session_ids if active_session_ids else False
            result.append(
                FileHistoryEntry(
                    dir_name=d.name,
                    path=str(d),
                    size_bytes=0,
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
    # Build set of active session IDs for orphan detection
    active_session_ids = _get_active_session_ids()
    result = []
    try:
        for f in sorted(DEBUG_DIR.iterdir()):
            size = f.stat().st_size if f.is_file() else _dir_size(f)
            is_orphaned = f.stem not in active_session_ids if active_session_ids else False
            result.append(
                DebugEntry(name=f.name, path=str(f), size_bytes=size, is_orphaned=is_orphaned)
            )
    except (PermissionError, OSError):
        pass
    return result


def get_todos() -> list[TodoEntry]:
    """Get per-session todo/task entries.

    Claude Code >= 2.1 stores task lists under ``tasks/<sessionId>/<n>.json``
    (one directory per session). Older versions used flat ``todos/*.json`` files.
    Each session directory (or legacy file) becomes one entry.
    """
    active_session_ids = _get_active_session_ids()
    result = []
    if TASKS_DIR.exists():
        try:
            for d in sorted(TASKS_DIR.iterdir()):
                if not d.is_dir():
                    continue
                session_id = d.name
                is_orphaned = session_id not in active_session_ids if active_session_ids else False
                result.append(
                    TodoEntry(name=session_id, path=str(d), size_bytes=_dir_size(d), is_orphaned=is_orphaned)
                )
        except (PermissionError, OSError):
            pass
        return result
    # Legacy fallback: flat todos/<sessionId>-agent-<id>.json files.
    if not TODOS_DIR.exists():
        return []
    try:
        for f in sorted(TODOS_DIR.iterdir()):
            size = f.stat().st_size if f.is_file() else _dir_size(f)
            session_id = f.stem.split("-agent-")[0] if "-agent-" in f.stem else f.stem
            is_orphaned = session_id not in active_session_ids if active_session_ids else False
            result.append(
                TodoEntry(name=f.name, path=str(f), size_bytes=size, is_orphaned=is_orphaned)
            )
    except (PermissionError, OSError):
        pass
    return result


def _get_active_session_ids() -> set[str]:
    """Get set of all active session IDs from project directories.

    Uses a recursive walk so nested (e.g. subagent) session files are also
    counted — otherwise their task/file-history entries look orphaned.
    """
    ids = set()
    if PROJECTS_DIR.exists():
        try:
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir():
                    for jsonl in d.rglob("*.jsonl"):
                        ids.add(jsonl.stem)
        except (PermissionError, OSError):
            pass
    return ids


def get_session_to_project_map() -> dict[str, str]:
    """Build session_id → project_path mapping."""
    mapping: dict[str, str] = {}
    encoded_to_paths = _build_encoded_to_paths_map()
    if PROJECTS_DIR.exists():
        try:
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir():
                    project_path = _project_label_for_dir(d.name, encoded_to_paths)
                    for jsonl in d.glob("*.jsonl"):
                        mapping[jsonl.stem] = project_path
        except (PermissionError, OSError):
            pass
    return mapping


def get_stats() -> Stats:
    """Calculate overall statistics.

    Computes shared data once to avoid redundant file parsing.
    """
    projects = get_projects()
    project_paths = {p.path for p in projects}
    sessions = get_sessions()

    # Compute active session IDs once for orphan detection
    active_ids = _get_active_session_ids()

    # Count file history
    fh_total, fh_orphaned = 0, 0
    if FILE_HISTORY_DIR.exists():
        try:
            for d in FILE_HISTORY_DIR.iterdir():
                if d.is_dir():
                    fh_total += 1
                    if d.name not in active_ids:
                        fh_orphaned += 1
        except (PermissionError, OSError):
            pass

    # Count debug files
    db_total, db_orphaned = 0, 0
    if DEBUG_DIR.exists():
        try:
            for f in DEBUG_DIR.iterdir():
                db_total += 1
                if f.stem not in active_ids:
                    db_orphaned += 1
        except (PermissionError, OSError):
            pass

    # Count todo/task entries (tasks/<sessionId>/ dirs, or legacy todos/ files)
    td_total, td_orphaned = 0, 0
    if TASKS_DIR.exists():
        try:
            for d in TASKS_DIR.iterdir():
                if not d.is_dir():
                    continue
                td_total += 1
                if d.name not in active_ids:
                    td_orphaned += 1
        except (PermissionError, OSError):
            pass
    elif TODOS_DIR.exists():
        try:
            for f in TODOS_DIR.iterdir():
                td_total += 1
                session_id = f.stem.split("-agent-")[0] if "-agent-" in f.stem else f.stem
                if session_id not in active_ids:
                    td_orphaned += 1
        except (PermissionError, OSError):
            pass

    return Stats(
        total_projects=len(projects),
        total_sessions=len(sessions),
        total_file_history=fh_total,
        total_debug=db_total,
        total_todos=td_total,
        orphaned_sessions=sum(1 for s in sessions if s.is_orphaned),
        orphaned_file_history=fh_orphaned,
        orphaned_debug=db_orphaned,
        orphaned_todos=td_orphaned,
        claude_dir_size=_dir_size(CLAUDE_DIR) if CLAUDE_DIR.exists() else 0,
        projects_dir_size=_dir_size(PROJECTS_DIR) if PROJECTS_DIR.exists() else 0,
    )


# Cached result of the expensive scan that parses token usage out of every
# session JSONL. Reused across daily/weekly/monthly so one screen refresh scans
# the tree once instead of three times. Cleared by refresh_usage_cache().
_usage_scan_cache: dict[str, dict] | None = None


def refresh_usage_cache() -> None:
    """Drop the cached token-usage scan (call when the user refreshes)."""
    global _usage_scan_cache
    _usage_scan_cache = None


def _collect_msg_usage() -> dict[str, dict]:
    """Scan all session JSONL once: {message_id: {usage, model, ts_str}}.

    Streaming writes several JSONL lines per API call with the same id; the last
    one carries the final counts, so keeping the last entry per id deduplicates.
    """
    global _usage_scan_cache
    if _usage_scan_cache is not None:
        return _usage_scan_cache
    from asm.services.pricing import is_billable

    msg_last: dict[str, dict] = {}
    if PROJECTS_DIR.exists():
        for d in PROJECTS_DIR.iterdir():
            if not d.is_dir():
                continue
            for jsonl in d.rglob("*.jsonl"):
                try:
                    with open(jsonl) as f:
                        for line in f:
                            try:
                                msg = json.loads(line)
                                if msg.get("type") != "assistant":
                                    continue
                                m = msg.get("message", {})
                                usage = m.get("usage")
                                model = m.get("model", "")
                                ts_str = msg.get("timestamp", "")
                                msg_id = m.get("id", "")
                                if not usage or not ts_str or not msg_id:
                                    continue
                                if not is_billable(model):
                                    continue
                                msg_last[msg_id] = {"usage": usage, "model": model, "ts_str": ts_str}
                            except (json.JSONDecodeError, KeyError):
                                continue
                except OSError:
                    continue
    _usage_scan_cache = msg_last
    return msg_last


def _period_key(dt, period: str) -> str:
    from datetime import timedelta
    if period == "monthly":
        return dt.strftime("%Y-%m")
    if period == "weekly":
        start = dt - timedelta(days=dt.weekday())  # ISO week start (Monday)
        return start.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def _aggregate_period(msg_last: dict[str, dict], period: str) -> list[dict]:
    from collections import defaultdict
    from datetime import datetime

    from asm.services.pricing import calc_cost as _calc_cost

    agg: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_create_tokens": 0,
        "cost": 0.0, "messages": 0,
    }))
    for info in msg_last.values():
        try:
            dt = datetime.fromisoformat(info["ts_str"].replace("Z", "+00:00"))
        except ValueError:
            continue
        usage = info["usage"]
        model = info["model"]
        pk = _period_key(dt, period)
        short_model = model.replace("claude-", "").split("-2025")[0].split("-2026")[0]
        entry = agg[pk][short_model]
        entry["input_tokens"] += usage.get("input_tokens", 0)
        entry["output_tokens"] += usage.get("output_tokens", 0)
        entry["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
        entry["cache_create_tokens"] += usage.get("cache_creation_input_tokens", 0)
        entry["cost"] += _calc_cost(usage, model)
        entry["messages"] += 1

    result = []
    for pk in sorted(agg.keys(), reverse=True):
        models = agg[pk]
        result.append({
            "period": pk,
            "total_cost": sum(m["cost"] for m in models.values()),
            "total_input": sum(m["input_tokens"] for m in models.values()),
            "total_output": sum(m["output_tokens"] for m in models.values()),
            "total_cache": sum(m["cache_read_tokens"] for m in models.values()),
            "total_messages": sum(m["messages"] for m in models.values()),
            "models": dict(models),
        })
    return result


def get_period_usage(period: str = "daily") -> list[dict]:
    """Token usage grouped by period ('daily' | 'weekly' | 'monthly')."""
    return _aggregate_period(_collect_msg_usage(), period)


def get_all_period_usage() -> dict[str, list[dict]]:
    """All three period groupings from a single scan (for the dashboard)."""
    msg_last = _collect_msg_usage()
    return {p: _aggregate_period(msg_last, p) for p in ("daily", "weekly", "monthly")}


def get_usage_data() -> dict:
    """Get usage/cost data from .claude.json and history.jsonl."""
    from collections import defaultdict
    from datetime import datetime

    data = load_claude_json()
    projects = data.get("projects", {})

    # Per-project costs
    project_costs = []
    model_totals: dict[str, dict] = {}
    total_cost = 0.0

    for path_str, config in projects.items():
        cost = config.get("lastCost") or 0
        total_cost += cost
        if cost > 0:
            project_costs.append({
                "path": path_str,
                "name": Path(path_str).name or path_str,
                "cost": cost,
                "duration": config.get("lastDuration") or 0,
            })
        # Model usage aggregation
        usage = config.get("lastModelUsage", {})
        for model, stats in usage.items():
            if model not in model_totals:
                model_totals[model] = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "costUSD": 0}
            for k in model_totals[model]:
                model_totals[model][k] += stats.get(k, 0)

    project_costs.sort(key=lambda x: x["cost"], reverse=True)

    # Daily sessions from history.jsonl
    sessions_by_day: dict[str, int] = defaultdict(int)
    history_path = CLAUDE_DIR / "history.jsonl"
    if history_path.exists():
        try:
            with open(history_path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        ts = d.get("timestamp", 0)
                        if ts:
                            dt = datetime.fromtimestamp(ts / 1000)
                            sessions_by_day[dt.strftime("%Y-%m-%d")] += 1
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass

    return {
        "total_cost": total_cost,
        "project_costs": project_costs[:15],
        "model_totals": model_totals,
        "sessions_by_day": dict(sorted(sessions_by_day.items(), reverse=True)[:14]),
        "total_sessions_ever": sum(sessions_by_day.values()),
        "first_use": data.get("firstStartTime", ""),
        "num_startups": data.get("numStartups", 0),
    }


def get_project_sessions(project_path: str) -> list[SessionDetail]:
    """Get sessions for one project.

    Claude Code >= 2.1 maintains a ``sessions-index.json`` per project dir with
    rich metadata (summary, firstPrompt, git branch, mtime). We prefer it and
    fall back to parsing the JSONL files directly for older layouts.
    """
    project_dir = _resolve_project_dir(project_path)
    if not project_dir:
        return []
    encoded = project_dir.name

    # The actual .jsonl files are the source of truth (those are viewable);
    # sessions-index.json only enriches them with summary/branch metadata.
    index = _load_session_index(project_dir)

    result = []
    for jsonl in project_dir.glob("*.jsonl"):
        try:
            stat = jsonl.stat()
        except OSError:
            continue
        session_id = jsonl.stem
        meta = index.get(session_id)
        if meta:
            summary = meta.get("summary") or meta.get("firstPrompt") or f"(session {session_id[:8]})"
            first_prompt = (meta.get("firstPrompt") or "")[:120]
            git_branch = meta.get("gitBranch", "") or ""
        else:
            first_prompt, ai_title = _scan_jsonl_summary(jsonl)
            summary = ai_title or first_prompt or f"(session {session_id[:8]})"
            git_branch = ""
        result.append(
            SessionDetail(
                session_id=session_id,
                summary=summary[:120],
                last_modified=stat.st_mtime,
                file_size=stat.st_size,
                first_prompt=first_prompt,
                git_branch=git_branch,
                project_dir=encoded,
            )
        )
    result.sort(key=lambda s: s.last_modified, reverse=True)
    return result


def _load_session_index(project_dir: Path) -> dict[str, dict]:
    """Load sessions-index.json into a {sessionId: entry} map (empty if absent)."""
    index_path = project_dir / "sessions-index.json"
    if not index_path.exists():
        return {}
    try:
        entries = json.loads(index_path.read_text()).get("entries", [])
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        e["sessionId"]: e
        for e in entries
        if isinstance(e, dict) and e.get("sessionId")
    }


def _scan_jsonl_summary(jsonl: Path) -> tuple[str, str]:
    """Return (first_prompt, ai_title) by scanning a session JSONL file."""
    first_prompt = ""
    ai_title = ""
    try:
        with open(jsonl) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mtype = msg.get("type")
                if mtype == "ai-title" and not ai_title:
                    ai_title = (msg.get("aiTitle") or "")[:120]
                elif mtype == "user" and not msg.get("isMeta") and not first_prompt:
                    content = msg.get("message", {}).get("content", "")
                    if isinstance(content, str):
                        if content and not content.startswith("<"):
                            first_prompt = content[:120]
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text and not text.startswith("<"):
                                    first_prompt = text[:120]
                                    break
                if ai_title and first_prompt:
                    break
    except OSError:
        pass
    return first_prompt, ai_title


def find_duplicate_sessions() -> dict[str, list[str]]:
    """Find session ids that appear in more than one project directory.

    Returns ``{session_id: [project_dir_name, ...]}`` for ids present in 2+ dirs
    (e.g. left over from session migration/copy). Only the top level of each
    project dir is scanned.
    """
    from collections import defaultdict

    id_to_dirs: dict[str, list[str]] = defaultdict(list)
    if not PROJECTS_DIR.exists():
        return {}
    try:
        for d in PROJECTS_DIR.iterdir():
            if not d.is_dir():
                continue
            for jsonl in d.glob("*.jsonl"):
                id_to_dirs[jsonl.stem].append(d.name)
    except (PermissionError, OSError):
        pass
    return {sid: dirs for sid, dirs in id_to_dirs.items() if len(dirs) > 1}


def _session_has_conversation(jsonl: Path) -> bool:
    """True if a session file has any user/assistant message with content."""
    try:
        with open(jsonl) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") in ("user", "assistant"):
                    if _extract_text_content(msg.get("message", {})):
                        return True
    except OSError:
        return True  # err on the safe side — don't flag as empty
    return False


def find_empty_sessions(size_cap: int = 16384) -> list[dict]:
    """Find 'stub' session files that have no actual conversation.

    These are sessions with only an ai-title / pr-link / metadata and no
    user/assistant turns (they can't be resumed). Only files up to ``size_cap``
    bytes are inspected — a real conversation is far larger, so this bounds the
    scan; emptiness itself is confirmed by parsing.
    Returns ``[{session_id, project_dir, path, title}]``.
    """
    result: list[dict] = []
    if not PROJECTS_DIR.exists():
        return result
    try:
        for d in PROJECTS_DIR.iterdir():
            if not d.is_dir():
                continue
            for jsonl in d.glob("*.jsonl"):
                try:
                    if jsonl.stat().st_size > size_cap:
                        continue
                except OSError:
                    continue
                if _session_has_conversation(jsonl):
                    continue
                _, title = _scan_jsonl_summary(jsonl)
                result.append({
                    "session_id": jsonl.stem,
                    "project_dir": d.name,
                    "path": str(jsonl),
                    "title": title,
                })
    except (PermissionError, OSError):
        pass
    return result


def remove_project_from_json(project_path: str) -> bool:
    """Remove a project entry from .claude.json (atomic write)."""
    import tempfile
    data = load_claude_json()
    projects = data.get("projects", {})
    if project_path in projects:
        del projects[project_path]
        data["projects"] = projects
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=str(CLAUDE_JSON.parent), suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(CLAUDE_JSON))
            return True
        except OSError:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return False
    return False
