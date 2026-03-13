"""Shared utility functions for cc-tui."""


def format_bytes(size: int) -> str:
    """Format byte size to human-readable string."""
    if size < 1024:
        return f"{size} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"
