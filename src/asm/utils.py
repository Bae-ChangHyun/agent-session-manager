"""Shared utility functions and display limits for asm."""

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
