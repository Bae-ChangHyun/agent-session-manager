"""Full-text search over session bodies.

The project filter matches session *titles* instantly (see ``ProjectsScreen``);
this module backs the heavier full-text pass that scans the actual conversation
JSONL bodies so a query can find sessions where the term only appears mid-chat.

ripgrep is used when available (fast, literal, case-insensitive) with a plain
Python scan as a fallback. Claude stores one ``<session_id>.jsonl`` per project
dir, so a content hit is identified by the file stem; Codex stores global
``rollout-*.jsonl`` files, identified by absolute path (matching
``SessionDetail.project_dir`` for Codex sessions).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from asm.models import CODEX_SESSIONS_DIR, PROJECTS_DIR

# Cap a single scan so a huge ~/.claude never freezes the filter box. ripgrep
# finishes well under this on normal data; the Python fallback is bounded by
# file count instead.
_GREP_TIMEOUT = 15


def _ripgrep_files(query: str, root: Path, glob: str) -> list[Path] | None:
    """Files under ``root`` matching ``glob`` whose contents contain ``query``.

    Case-insensitive, literal (fixed-string) match. Returns ``None`` when
    ripgrep is unavailable so callers fall back to a Python scan; returns an
    empty list on timeout or ripgrep error.
    """
    rg = shutil.which("rg")
    if rg is None:
        return None
    try:
        proc = subprocess.run(
            [rg, "-l", "-i", "-F", "-g", glob, "--", query, str(root)],
            capture_output=True,
            text=True,
            timeout=_GREP_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    # exit 0 = matches, 1 = no matches (empty stdout), 2 = error.
    if proc.returncode not in (0, 1):
        return []
    return [Path(line) for line in proc.stdout.splitlines() if line]


def _python_grep_files(query: str, root: Path, glob: str) -> list[Path]:
    """Fallback content scan without ripgrep (slower, bounded by file count)."""
    needle = query.casefold()
    hits: list[Path] = []
    try:
        for f in root.rglob(glob):
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    if any(needle in line.casefold() for line in fh):
                        hits.append(f)
            except OSError:
                continue
    except OSError:
        pass
    return hits


def _grep_files(query: str, root: Path, glob: str) -> list[Path]:
    files = _ripgrep_files(query, root, glob)
    if files is None:
        files = _python_grep_files(query, root, glob)
    return files


def search_claude_session_ids(query: str) -> set[str]:
    """Claude session ids whose JSONL body contains ``query`` (case-insensitive)."""
    query = query.strip()
    if not query or not PROJECTS_DIR.exists():
        return set()
    return {f.stem for f in _grep_files(query, PROJECTS_DIR, "*.jsonl")}


def search_codex_rollout_paths(query: str) -> set[str]:
    """Absolute paths of Codex rollout files whose body contains ``query``."""
    query = query.strip()
    if not query or not CODEX_SESSIONS_DIR.exists():
        return set()
    return {str(f) for f in _grep_files(query, CODEX_SESSIONS_DIR, "rollout-*.jsonl")}
