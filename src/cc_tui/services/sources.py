"""Data-source selection for the TUI (Claude Code vs OpenAI Codex)."""

from __future__ import annotations

from cc_tui.services import claude_data, codex_data

CLAUDE = "claude"
CODEX = "codex"


def data_module(source: str):
    """Return the data-service module for the given source.

    Both modules expose get_stats / get_usage_data / get_period_usage /
    get_project_sessions / get_session_messages with compatible signatures.
    """
    return codex_data if source == CODEX else claude_data
