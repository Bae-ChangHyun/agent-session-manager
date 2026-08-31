"""Tests for the Codex data source and OpenAI pricing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

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

    def test_find_session_requires_exact_or_unique_prefix(self, tmp_path: Path):
        sessions = tmp_path / "sessions" / "2026" / "06" / "01"
        _write_rollout(sessions / "rollout-2026-06-01T09-00-00-abc111.jsonl", "abc111", "/work/a", "gpt-5", {}, "a")
        _write_rollout(sessions / "rollout-2026-06-01T09-00-01-abc222.jsonl", "abc222", "/work/b", "gpt-5", {}, "b")
        codex_data.refresh()

        with patch.object(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "sessions"):
            assert codex_data.find_session("abc111").session_id == "abc111"
            assert codex_data.find_session("abc2").session_id == "abc222"
            with pytest.raises(codex_data.AmbiguousSessionIdError, match="multiple Codex sessions"):
                codex_data.find_session("abc")
            assert codex_data.find_session("2026") is None

    def test_find_session_fails_when_a_codex_home_scan_is_incomplete(
        self, monkeypatch, tmp_path: Path
    ):
        good = tmp_path / "good"
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        _write_rollout(
            good / "2026" / "06" / "01" / "rollout-good.jsonl",
            "shared-prefix-one",
            "/work/a",
            "gpt-5",
            {},
            "a",
        )
        original_rglob = Path.rglob

        def fail_blocked(path: Path, pattern: str):
            if path == blocked:
                raise PermissionError("denied")
            return original_rglob(path, pattern)

        monkeypatch.setattr(codex_data, "_session_dirs", lambda: [good, blocked])
        monkeypatch.setattr(Path, "rglob", fail_blocked)

        with pytest.raises(codex_data.CodexScanError, match="Unable to scan Codex sessions"):
            codex_data.find_session("shared-prefix")

    def test_find_session_fails_when_any_rollout_is_malformed(self, monkeypatch, tmp_path: Path):
        sessions = tmp_path / "sessions"
        _write_rollout(
            sessions / "2026" / "06" / "01" / "rollout-good.jsonl",
            "shared-prefix-one",
            "/work/a",
            "gpt-5",
            {},
            "a",
        )
        malformed = sessions / "2026" / "06" / "01" / "rollout-broken.jsonl"
        malformed.write_text("{broken\n")
        monkeypatch.setattr(codex_data, "_session_dirs", lambda: [sessions])

        with pytest.raises(codex_data.CodexScanError, match="Malformed Codex session"):
            codex_data.find_session("shared-prefix")

    def test_total_session_count_fails_when_a_home_scan_is_incomplete(
        self, monkeypatch, tmp_path: Path
    ):
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        monkeypatch.setattr(codex_data, "_session_dirs", lambda: [blocked])
        monkeypatch.setattr(Path, "rglob", lambda *_: (_ for _ in ()).throw(PermissionError("denied")))

        with pytest.raises(codex_data.CodexScanError, match="Unable to scan Codex sessions"):
            codex_data.total_session_count()

    @pytest.mark.parametrize("session_ref", ["../rollout", "../../history", "/tmp/session", r"..\rollout"])
    def test_find_session_rejects_path_syntax(self, tmp_path: Path, session_ref: str):
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        with (
            patch.object(codex_data, "CODEX_SESSIONS_DIR", sessions),
            pytest.raises(ValueError, match="session id"),
        ):
            codex_data.find_session(session_ref)

    def test_move_session_stops_when_snapshot_fails(self, monkeypatch, tmp_path: Path):
        rollout = tmp_path / "sessions" / "2026" / "06" / "01" / "rollout-test.jsonl"
        _write_rollout(rollout, "move-me", "/work/old", "gpt-5", {}, "move")
        before = rollout.read_text()
        monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "sessions")
        monkeypatch.setattr("asm.services.recovery.create_recovery_snapshot", lambda *_: None)

        assert codex_data.move_session(str(rollout), "/work/new") is False
        assert rollout.read_text() == before

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


def _write_rollout_real_layout(path: Path, session_id: str, cwd: str, turn_models: list[str], usage: dict | None):
    """Rollout matching real Codex output: model only on turn_context lines."""
    lines: list[dict] = [
        {"timestamp": "2026-06-01T09:00:00.000Z", "type": "session_meta",
         "payload": {"id": session_id, "timestamp": "2026-06-01T09:00:00.000Z", "cwd": cwd,
                     "model_provider": "openai", "git": {"branch": "main"}}},
    ]
    for m in turn_models:
        lines.append({"timestamp": "2026-06-01T09:00:01.000Z", "type": "turn_context",
                      "payload": {"turn_id": "t", "cwd": cwd, "model": m}})
    if usage is not None:
        lines.append({"timestamp": "2026-06-01T09:00:03.000Z", "type": "event_msg",
                      "payload": {"type": "token_count", "info": {"total_token_usage": usage}}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


class TestCodexModelDetection:
    def test_model_from_turn_context_last_wins(self, tmp_path: Path):
        sessions = tmp_path / "sessions" / "2026" / "06" / "01"
        _write_rollout_real_layout(
            sessions / "rollout-2026-06-01T09-00-00-cccc.jsonl",
            "cccc", "/work/proj-c", ["gpt-5.4-mini", "gpt-5.5"],
            {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 1_000_000},
        )
        codex_data.refresh()
        with patch.object(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "sessions"):
            usage = codex_data.get_usage_data()
        assert set(usage["model_totals"]) == {"gpt-5.5"}
        assert round(usage["total_cost"], 2) == 5.0

    def test_missing_model_is_labeled_unknown(self, tmp_path: Path):
        sessions = tmp_path / "sessions" / "2026" / "06" / "01"
        _write_rollout_real_layout(
            sessions / "rollout-2026-06-01T09-00-00-dddd.jsonl",
            "dddd", "/work/proj-d", [],
            {"input_tokens": 1_000, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 1_000},
        )
        codex_data.refresh()
        with patch.object(codex_data, "CODEX_SESSIONS_DIR", tmp_path / "sessions"):
            usage = codex_data.get_usage_data()
            periods = codex_data.get_period_usage("daily")
        assert set(usage["model_totals"]) == {codex_data.UNKNOWN_MODEL}
        assert set(periods[0]["models"]) == {codex_data.UNKNOWN_MODEL}


# --- Multiple Codex homes (one per account) ---


def test_scans_every_codex_home(monkeypatch, tmp_path):
    from asm import models
    from asm.services import codex_data

    primary = tmp_path / ".codex"
    second = tmp_path / ".codex-work"
    _write_rollout_real_layout(
        primary / "sessions" / "2026" / "06" / "01" / "rollout-2026-06-01T09-00-00-aaaa.jsonl",
        "aaaa", "/work/a", ["gpt-5.5"],
        {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10, "total_tokens": 110},
    )
    _write_rollout_real_layout(
        second / "sessions" / "2026" / "06" / "02" / "rollout-2026-06-02T09-00-00-bbbb.jsonl",
        "bbbb", "/work/b", ["gpt-5.5"],
        {"input_tokens": 200, "cached_input_tokens": 0, "output_tokens": 20, "total_tokens": 220},
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(models, "CODEX_DIR", primary)
    monkeypatch.setattr(models, "_codex_home_override", None)
    monkeypatch.delenv("ASM_CODEX_HOMES", raising=False)
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", primary / "sessions")
    codex_data.refresh()

    assert codex_data.is_available()
    assert codex_data.total_session_count() == 2
    assert {p.path for p in codex_data.get_projects()} == {"/work/a", "/work/b"}

    codex_data.refresh()


def test_repointed_sessions_dir_stays_pinned(monkeypatch, tmp_path):
    """Tests (and --codex-home) pin one dir; discovery must not widen it."""
    from asm import models
    from asm.services import codex_data

    pinned = tmp_path / "pinned"
    _write_rollout_real_layout(
        pinned / "2026" / "06" / "01" / "rollout-2026-06-01T09-00-00-cccc.jsonl",
        "cccc", "/work/c", ["gpt-5.5"], None,
    )
    (tmp_path / ".codex-other" / "sessions" / "2026" / "06").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(models, "CODEX_DIR", tmp_path / ".codex")
    monkeypatch.setattr(codex_data, "CODEX_SESSIONS_DIR", pinned)
    codex_data.refresh()

    assert codex_data._session_dirs() == [pinned]
    assert codex_data.total_session_count() == 1

    codex_data.refresh()
