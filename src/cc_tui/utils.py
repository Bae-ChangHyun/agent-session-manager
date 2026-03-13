"""Shared utility functions for cc-tui."""


def format_bytes(size: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
