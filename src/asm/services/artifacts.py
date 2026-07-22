"""Find Claude Code artifact publications recorded in session JSONLs.

Publishing with the Artifact tool leaves a ``tool_use`` (name ``Artifact``,
input carrying file_path/title/description) and a matching ``tool_result``
whose text contains the published claude.ai URL. There is no separate local
registry, so this scans the session files — candidate files are pre-filtered
with the shared ripgrep helper, then only those are parsed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from asm.models import PROJECTS_DIR
from asm.services.search import _grep_files

_URL_RE = re.compile(r"https://claude\.ai/\S*artifact\S*", re.IGNORECASE)


@dataclass
class ArtifactInfo:
    """One published artifact (latest publication wins per URL)."""

    url: str
    title: str
    description: str = ""
    favicon: str = ""
    file_path: str = ""
    project_dir: str = ""
    session_id: str = ""
    published: float = 0.0


def list_artifacts() -> list[ArtifactInfo]:
    """All artifacts published from Claude Code sessions, newest first."""
    if not PROJECTS_DIR.exists():
        return []
    by_url: dict[str, ArtifactInfo] = {}
    for f in _grep_files('"name":"Artifact"', PROJECTS_DIR, "*.jsonl"):
        for info in _parse_session_file(f):
            prev = by_url.get(info.url)
            if prev is None or info.published >= prev.published:
                by_url[info.url] = info
    return sorted(by_url.values(), key=lambda a: a.published, reverse=True)


def _parse_session_file(path: Path) -> list[ArtifactInfo]:
    try:
        rel = path.relative_to(PROJECTS_DIR)
        project_dir = rel.parts[0]
    except ValueError:
        project_dir = ""
    pending: dict[str, tuple[dict, float]] = {}
    found: list[ArtifactInfo] = []
    try:
        with open(path) as fh:
            for line in fh:
                if "Artifact" not in line and "tool_use_id" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = (obj.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                ts = _parse_ts(obj.get("timestamp", ""))
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use" and block.get("name") == "Artifact":
                        pending[block.get("id", "")] = (block.get("input") or {}, ts)
                    elif block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                        inp, use_ts = pending.pop(block["tool_use_id"])
                        url = _extract_url(block.get("content"))
                        if not url:
                            continue  # list/failed calls publish nothing
                        found.append(
                            ArtifactInfo(
                                url=url,
                                title=_title_for(inp),
                                description=inp.get("description", "") or "",
                                favicon=inp.get("favicon", "") or "",
                                file_path=inp.get("file_path", "") or "",
                                project_dir=project_dir,
                                session_id=path.stem,
                                published=ts or use_ts,
                            )
                        )
    except OSError:
        pass
    return found


def _title_for(inp: dict) -> str:
    for key in ("title", "label", "description"):
        val = inp.get(key)
        if val:
            return str(val)
    fp = inp.get("file_path", "")
    return Path(fp).stem if fp else "(untitled)"


def _extract_url(content) -> str:
    if isinstance(content, list):
        content = " ".join(
            b.get("text", "") for b in content if isinstance(b, dict)
        )
    if not isinstance(content, str):
        return ""
    m = _URL_RE.search(content)
    return m.group(0).rstrip(".,)") if m else ""


def _parse_ts(ts_str: str) -> float:
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
