"""Shared utility functions and display limits for asm."""

from __future__ import annotations

import sys
from pathlib import Path

# Shared display caps (dashboard + CLI aggregate the same service data).
TOP_PROJECT_LIMIT = 15       # rows kept in the per-project cost ranking
TOP_PROJECT_CHART_ROWS = 10  # rows actually rendered in the cost chart/tables
RECENT_DAYS_LIMIT = 14       # days kept in sessions-per-day
SUMMARY_MAX_CHARS = 120      # session title/first-prompt truncation


def format_bytes(size: int) -> str:
    """Format byte size to human-readable string."""
    if size < 1024:
        return f"{size} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


def dir_size(path: Path) -> int:
    """Total size of a directory tree.

    Uses ``du -sb`` on Linux for speed, falls back to a pure-Python walk on
    Windows / macOS / when the command fails. (macOS ``du`` has no ``-b``,
    so it's excluded to avoid a failing subprocess per directory.)
    """
    if sys.platform == "linux":
        import subprocess
        try:
            result = subprocess.run(
                ["du", "-sb", "--", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0])
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
            pass
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except (PermissionError, OSError):
        pass
    return total
