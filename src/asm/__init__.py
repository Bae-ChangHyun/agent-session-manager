"""asm: Terminal UI for managing Claude Code & Codex sessions."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-session-manager")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+dev"
