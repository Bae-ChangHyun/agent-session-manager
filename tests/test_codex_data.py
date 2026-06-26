"""Tests for the Codex data source and OpenAI pricing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from asm.services import codex_data
from asm.services import pricing


def _write_rollout(path: Path, session_id: str, cwd: str, model: str, usage: dict, first_user: str):
    lines = [
        {"timestamp": "2026-06-01T09:00:00.000Z", "type": "session_meta",
         "payload": {"id": session_id, "timestamp": "2026-06-01T09:00:00.000Z", "cwd": cwd,
                     "model": model, "git": {"branch": "main"}}},
        {"timestamp": "2026-06-01T09:00:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": first_user}]}},
        {"timestamp": "2026-06-01T09:00:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "ok done"}]}},
        {"timestamp": "2026-06-01T09:00:03.000Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": usage}}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _setup(tmp_path: Path):
    sessions = tmp_path / "sessions" / "2026" / "06" / "01"
    _write_rollout(
        sessions / "rollout-2026-06-01T09-00-00-aaaa.jsonl",
        "aaaa", "/work/proj-a", "gpt-5.5",
        {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 1_000_000},
        "build the thing",
    )
    _write_rollout(
        sessions / "rollout-2026-06-01T09-30-00-bbbb.jsonl",
        "bbbb", "/work/proj-b", "gpt-5",
        {"input_tokens": 2_000, "cached_input_tokens": 1_000, "output_tokens": 500, "total_tokens": 2_500},
        "another task",
    )
    return tmp_path / "sessions"


class TestCodexData:
    def test_projects_and_sessions(self, tmp_path: Path):
        sessions = _setup(tmp_path)
        codex_data.refresh()
        with patch.object(codex_data, "CODEX_SESSIONS_DIR", sessions):
            assert codex_data.is_available()
            assert codex_data.total_session_count() == 2
            projects = codex_data.get_projects()
            paths = {p.path for p in projects}
            assert paths == {"/work/proj-a", "/work/proj-b"}

            ses = codex_data.get_project_sessions("/work/proj-a")
            assert len(ses) == 1
            assert ses[0].session_id == "aaaa"
            assert ses[0].summary == "build the thing"
            assert ses[0].git_branch == "main"

            msgs = codex_data.get_session_messages("aaaa", ses[0].project_dir)
            assert {m["type"] for m in msgs} == {"user", "assistant"}

    def test_get_sessions_by_paths_ignores_scan_limit(self, tmp_path: Path):
        sessions = _setup(tmp_path)
        codex_data.refresh()
        with patch.object(codex_data, "CODEX_SESSIONS_DIR", sessions):
            # Loading straight from a rollout path works regardless of how many
            # recent sessions the scan cap would cover; bad paths are skipped.
            rollout = sessions / "2026" / "06" / "01" / "rollout-2026-06-01T09-00-00-aaaa.jsonl"
            loaded = codex_data.get_sessions_by_paths([str(rollout), "/nope/missing.jsonl"])
            assert len(loaded) == 1
            assert loaded[0].session_id == "aaaa"
            assert loaded[0].cwd == "/work/proj-a"
            assert loaded[0].project_dir == str(rollout)

    def test_period_usage_cost(self, tmp_path: Path):
        sessions = _setup(tmp_path)
        codex_data.refresh()
        with patch.object(codex_data, "CODEX_SESSIONS_DIR", sessions):
            usage = codex_data.get_usage_data()
        # proj-a: 1M input gpt-5.5 -> $5.00; proj-b small -> a few cents
        assert usage["total_cost"] > 5.0
        top = usage["project_costs"][0]
        assert top["path"] == "/work/proj-a"
        assert round(top["cost"], 2) == 5.0


class TestOpenAIPricing:
    def test_gpt_rates(self):
        u = {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0}
        assert pricing.calc_openai_cost(u, "gpt-5.5") == 5.0
        assert pricing.calc_openai_cost(u, "gpt-5") == 1.25
        # dated suffix is stripped
        assert pricing.calc_openai_cost(u, "gpt-5.5-2026-04-23") == 5.0
        # cached input billed cheaper
        u2 = {"input_tokens": 1_000_000, "cached_input_tokens": 1_000_000, "output_tokens": 0}
        assert pricing.calc_openai_cost(u2, "gpt-5.5") == 0.5
