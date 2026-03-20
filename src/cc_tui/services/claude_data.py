"""Service for reading Claude Code data from filesystem and SDK."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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
    except Exception:
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
    """Get todo file entries."""
    if not TODOS_DIR.exists():
        return []
    active_session_ids = _get_active_session_ids()
    result = []
    try:
        for f in sorted(TODOS_DIR.iterdir()):
            size = f.stat().st_size if f.is_file() else _dir_size(f)
            # Todo filenames: {UUID}-agent-{UUID}.json → extract first UUID
            session_id = f.stem.split("-agent-")[0] if "-agent-" in f.stem else f.stem
            is_orphaned = session_id not in active_session_ids if active_session_ids else False
            result.append(
                TodoEntry(name=f.name, path=str(f), size_bytes=size, is_orphaned=is_orphaned)
            )
    except (PermissionError, OSError):
        pass
    return result


def _get_active_session_ids() -> set[str]:
    """Get set of all active session IDs from project directories."""
    ids = set()
    if PROJECTS_DIR.exists():
        try:
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir():
                    for jsonl in d.glob("*.jsonl"):
                        ids.add(jsonl.stem)
        except (PermissionError, OSError):
            pass
    return ids


def get_session_to_project_map() -> dict[str, str]:
    """Build session_id → project_path mapping."""
    mapping: dict[str, str] = {}
    project_paths = get_project_paths()
    encoded_to_path = {encode_path(p): p for p in project_paths}
    if PROJECTS_DIR.exists():
        try:
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir():
                    project_path = encoded_to_path.get(d.name, decode_path_hint(d.name))
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

    # Count todo files
    td_total, td_orphaned = 0, 0
    if TODOS_DIR.exists():
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


def get_period_usage(period: str = "daily") -> list[dict]:
    """Get token usage data grouped by period from JSONL session files.

    Parses assistant messages in all session files for model/usage/timestamp data.
    period: 'daily', 'weekly', 'monthly'
    """
    from collections import defaultdict
    from datetime import datetime, timedelta

    # Per-1M-token rates (USD).  Opus 4.5/4.6 is 3x cheaper than 4.0/4.1.
    model_cost_rates = {
        "input":        {"opus": 15, "opus45": 5,  "sonnet": 3,  "haiku": 1},
        "output":       {"opus": 75, "opus45": 25, "sonnet": 15, "haiku": 5},
        "cache_read":   {"opus": 1.5, "opus45": 0.50, "sonnet": 0.30, "haiku": 0.10},
        "cache_create": {"opus": 18.75, "opus45": 6.25, "sonnet": 3.75, "haiku": 1.25},
    }

    def _model_tier(model_name: str) -> str:
        if "opus" in model_name:
            # opus-4-5, opus-4-6 → new pricing; opus-4-0, opus-4-1 → old pricing
            if "opus-4-5" in model_name or "opus-4-6" in model_name:
                return "opus45"
            return "opus"
        if "haiku" in model_name:
            return "haiku"
        return "sonnet"

    def _calc_cost(usage: dict, tier: str) -> float:
        rates = model_cost_rates
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_create = usage.get("cache_creation_input_tokens", 0)
        return (
            inp * rates["input"][tier] / 1_000_000
            + out * rates["output"][tier] / 1_000_000
            + cache_read * rates["cache_read"][tier] / 1_000_000
            + cache_create * rates["cache_create"][tier] / 1_000_000
        )

    def _period_key(dt: datetime) -> str:
        if period == "monthly":
            return dt.strftime("%Y-%m")
        elif period == "weekly":
            # ISO week start (Monday)
            start = dt - timedelta(days=dt.weekday())
            return start.strftime("%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")

    # Aggregate: {period_key: {model: {input, output, cache_read, cache_create, cost}}}
    agg: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_create_tokens": 0,
        "cost": 0.0, "messages": 0,
    }))

    if not PROJECTS_DIR.exists():
        return []

    # First pass: collect last usage per message id (streaming writes
    # multiple JSONL lines per API call with the same usage; only the
    # last line carries the final output_tokens count).
    msg_last: dict[str, dict] = {}  # message_id -> {usage, model, ts_str}
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
                            # Keep last entry per message id (final streaming event)
                            msg_last[msg_id] = {
                                "usage": usage,
                                "model": model,
                                "ts_str": ts_str,
                            }
                        except (json.JSONDecodeError, KeyError):
                            continue
            except OSError:
                continue

    # Second pass: aggregate deduplicated entries
    for info in msg_last.values():
        usage = info["usage"]
        model = info["model"]
        ts_str = info["ts_str"]
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        pk = _period_key(dt)
        tier = _model_tier(model)
        short_model = model.replace("claude-", "").split("-2025")[0].split("-2026")[0]
        entry = agg[pk][short_model]
        entry["input_tokens"] += usage.get("input_tokens", 0)
        entry["output_tokens"] += usage.get("output_tokens", 0)
        entry["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
        entry["cache_create_tokens"] += usage.get("cache_creation_input_tokens", 0)
        entry["cost"] += _calc_cost(usage, tier)
        entry["messages"] += 1

    # Convert to sorted list
    result = []
    for pk in sorted(agg.keys(), reverse=True):
        models = agg[pk]
        total_cost = sum(m["cost"] for m in models.values())
        total_input = sum(m["input_tokens"] for m in models.values())
        total_output = sum(m["output_tokens"] for m in models.values())
        total_cache = sum(m["cache_read_tokens"] for m in models.values())
        total_msgs = sum(m["messages"] for m in models.values())
        result.append({
            "period": pk,
            "total_cost": total_cost,
            "total_input": total_input,
            "total_output": total_output,
            "total_cache": total_cache,
            "total_messages": total_msgs,
            "models": dict(models),
        })
    return result


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
    """Get sessions specifically for one project."""
    encoded = encode_path(project_path)
    project_dir = PROJECTS_DIR / encoded
    if not project_dir.exists():
        return []

    result = []
    for jsonl in sorted(project_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            stat = jsonl.stat()
            first_prompt = ""
            session_id = jsonl.stem
            with open(jsonl) as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "user" and not msg.get("isMeta"):
                            content = msg.get("message", {}).get("content", "")
                            if isinstance(content, str):
                                # Skip XML/command messages
                                if not content.startswith("<"):
                                    first_prompt = content[:120]
                                    break
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text = block.get("text", "")
                                        if not text.startswith("<"):
                                            first_prompt = text[:120]
                                            break
                                if first_prompt:
                                    break
                    except json.JSONDecodeError:
                        continue
            result.append(
                SessionDetail(
                    session_id=session_id,
                    summary=first_prompt or f"(session {session_id[:8]})",
                    last_modified=stat.st_mtime,
                    file_size=stat.st_size,
                    first_prompt=first_prompt,
                    project_dir=encoded,
                )
            )
        except OSError:
            continue
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
