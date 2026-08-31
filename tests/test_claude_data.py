"""Tests for Claude data service behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from asm.services.claude_data import get_session_messages, get_session_to_project_map


class TestSessionMessages:
    def test_get_session_messages_scopes_to_project_dir(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        left = projects_dir / "proj-left"
        right = projects_dir / "proj-right"
        left.mkdir(parents=True)
        right.mkdir(parents=True)

        session_id = "shared-session"
        (left / f"{session_id}.jsonl").write_text(
            '{"type":"user","message":{"content":"left project"}}\n'
        )
        (right / f"{session_id}.jsonl").write_text(
            '{"type":"user","message":{"content":"right project"}}\n'
        )

        with patch("asm.services.claude_data.PROJECTS_DIR", projects_dir):
            messages = get_session_messages(session_id, project_dir="proj-right", limit=10)

        assert messages == [{"type": "user", "content": "right project"}]

    def test_get_session_messages_rejects_path_traversal(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "proj"
        project_dir.mkdir(parents=True)
        outside = tmp_path / "history.jsonl"
        outside.write_text('{"type":"user","message":{"content":"private"}}\n')

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            pytest.raises(ValueError, match="session id"),
        ):
            get_session_messages("../../history", project_dir="proj", limit=10)


class TestProjectConfigTrust:
    def test_malformed_config_is_not_treated_as_empty_registry(self, tmp_path: Path):
        from asm.services.claude_data import ClaudeConfigError, get_sessions, load_claude_json

        claude_json = tmp_path / ".claude.json"
        claude_json.write_text("{broken")
        projects_dir = tmp_path / ".claude" / "projects"
        session_dir = projects_dir / "-work-live"
        session_dir.mkdir(parents=True)
        (session_dir / "session.jsonl").write_text("{}\n")

        with (
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
        ):
            with pytest.raises(ClaudeConfigError, match="Unable to read Claude project config"):
                load_claude_json()
            sessions = get_sessions()

        assert len(sessions) == 1
        assert sessions[0].is_orphaned is False

    def test_orphan_listing_requires_trusted_project_config(self, tmp_path: Path):
        from asm.services.claude_data import ClaudeConfigError, get_orphaned_sessions

        claude_json = tmp_path / ".claude.json"
        claude_json.write_text("{broken")
        projects_dir = tmp_path / ".claude" / "projects"
        (projects_dir / "-work-live").mkdir(parents=True)

        with (
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            pytest.raises(ClaudeConfigError, match="Unable to read Claude project config"),
        ):
            get_orphaned_sessions()

    def test_missing_config_does_not_make_existing_sessions_orphaned(self, tmp_path: Path):
        from asm.services.claude_data import ClaudeConfigError, get_orphaned_sessions, get_sessions

        claude_json = tmp_path / ".claude.json"
        projects_dir = tmp_path / ".claude" / "projects"
        session_dir = projects_dir / "-work-live"
        session_dir.mkdir(parents=True)

        with (
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
        ):
            sessions = get_sessions()
            with pytest.raises(ClaudeConfigError, match="Claude project config is missing"):
                get_orphaned_sessions()

        assert len(sessions) == 1
        assert sessions[0].is_orphaned is False

    def test_unreadable_config_stops_orphan_listing(self, tmp_path: Path):
        from asm.services.claude_data import ClaudeConfigError, get_orphaned_sessions

        claude_json = tmp_path / ".claude.json"
        claude_json.write_text("{}")
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)

        with (
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch.object(Path, "read_text", side_effect=PermissionError("denied")),
            pytest.raises(ClaudeConfigError, match="Unable to read Claude project config"),
        ):
            get_orphaned_sessions()


class TestSessionResolution:
    def test_resolve_session_ref_allows_only_unique_prefix(self, tmp_path: Path):
        from asm.services.claude_data import AmbiguousSessionIdError, resolve_session_ref

        projects_dir = tmp_path / "projects"
        left = projects_dir / "left"
        right = projects_dir / "right"
        left.mkdir(parents=True)
        right.mkdir(parents=True)
        (left / "abc111.jsonl").write_text("{}\n")
        (right / "abc222.jsonl").write_text("{}\n")

        with patch("asm.services.claude_data.PROJECTS_DIR", projects_dir):
            assert resolve_session_ref("abc1") == ("left", "abc111")
            with pytest.raises(AmbiguousSessionIdError, match="multiple Claude sessions"):
                resolve_session_ref("abc")
            assert resolve_session_ref("missing") is None

    @pytest.mark.parametrize("session_ref", ["../history", "../../history", "/tmp/session", r"..\history"])
    def test_resolve_session_ref_rejects_path_syntax(self, tmp_path: Path, session_ref: str):
        from asm.services.claude_data import resolve_session_ref

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            pytest.raises(ValueError, match="session id"),
        ):
            resolve_session_ref(session_ref)

    def test_resolve_session_ref_honors_project_scope(self, tmp_path: Path):
        from asm.services.claude_data import resolve_session_ref

        projects_dir = tmp_path / "projects"
        left = projects_dir / "left"
        right = projects_dir / "right"
        left.mkdir(parents=True)
        right.mkdir(parents=True)
        (left / "duplicate.jsonl").write_text("{}\n")
        (right / "duplicate.jsonl").write_text("{}\n")

        with patch("asm.services.claude_data.PROJECTS_DIR", projects_dir):
            assert resolve_session_ref("duplicate", project_ref="right") == (
                "right",
                "duplicate",
            )


class TestSessionProjectMap:
    def test_get_session_to_project_map_marks_ambiguous_encoded_dirs(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        encoded_dir = projects_dir / "-tmp-demo-app"
        encoded_dir.mkdir(parents=True)
        (encoded_dir / "session-1.jsonl").write_text("{}\n")

        fake_paths = {"/tmp/demo-app", "/tmp/demo_app"}

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("asm.services.claude_data.get_project_paths", return_value=fake_paths),
        ):
            mapping = get_session_to_project_map()

        assert mapping["session-1"].startswith("[ambiguous] ")
        assert "/tmp/demo-app" in mapping["session-1"]
        assert "/tmp/demo_app" in mapping["session-1"]


class TestProjectSessionResolution:
    """Regression tests for Claude Code >= 2.1 session/data layout changes."""

    def test_resolve_project_dir_stays_under_projects_dir(self, tmp_path: Path):
        # An absolute project path must resolve to its ENCODED dir under
        # PROJECTS_DIR, not collapse to the real (session-less) source folder.
        from asm.services.claude_data import _resolve_project_dir
        from asm.models import encode_path

        projects_dir = tmp_path / "projects"
        abs_path = "/work/my-proj"
        encoded = projects_dir / encode_path(abs_path)
        encoded.mkdir(parents=True)

        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(json.dumps({"projects": {abs_path: {}}}))

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
        ):
            resolved = _resolve_project_dir(abs_path)

        assert resolved is not None
        assert resolved.parent == projects_dir

    @pytest.mark.parametrize("project_ref", [".", "..", "left/right", r"left\right"])
    def test_resolve_project_dir_rejects_non_component_refs(
        self, tmp_path: Path, project_ref: str
    ):
        from asm.services.claude_data import _resolve_project_dir

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            pytest.raises(ValueError, match="project reference"),
        ):
            _resolve_project_dir(project_ref)

    def test_resolve_project_dir_rejects_symlink_escape(self, tmp_path: Path):
        from asm.services.claude_data import _resolve_project_dir

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (projects_dir / "linked").symlink_to(outside, target_is_directory=True)

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            pytest.raises(ValueError, match="project reference"),
        ):
            _resolve_project_dir("linked")

    def test_resolve_project_dir_accepts_unregistered_recorded_cwd(self, tmp_path: Path):
        from asm.services.claude_data import _resolve_project_dir
        from asm.models import encode_path

        projects_dir = tmp_path / "projects"
        project_path = "/work/imported"
        project_dir = projects_dir / encode_path(project_path)
        project_dir.mkdir(parents=True)
        (project_dir / "session.jsonl").write_text(
            json.dumps({"type": "user", "cwd": project_path}) + "\n"
        )

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("asm.services.claude_data.CLAUDE_JSON", tmp_path / "missing.json"),
        ):
            assert _resolve_project_dir(project_path) == project_dir

    def test_get_project_sessions_uses_index_and_jsonl(self, tmp_path: Path):
        from asm.services.claude_data import get_project_sessions
        from asm.models import encode_path

        projects_dir = tmp_path / "projects"
        abs_path = "/work/web-app"
        d = projects_dir / encode_path(abs_path)
        d.mkdir(parents=True)
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(json.dumps({"projects": {abs_path: {}}}))
        sid = "11111111-2222-3333-4444-555555555555"
        (d / f"{sid}.jsonl").write_text('{"type":"user","message":{"content":"hi"}}\n')
        (d / "sessions-index.json").write_text(json.dumps({
            "version": 1,
            "entries": [{"sessionId": sid, "summary": "indexed summary", "gitBranch": "main"}],
        }))

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("asm.services.claude_data.CLAUDE_JSON", claude_json),
        ):
            sessions = get_project_sessions(abs_path)

        assert len(sessions) == 1
        assert sessions[0].summary == "indexed summary"
        assert sessions[0].git_branch == "main"
        assert sessions[0].file_size > 0

    def test_get_todos_reads_tasks_dir(self, tmp_path: Path):
        from asm.services.claude_data import get_todos

        projects_dir = tmp_path / "projects"
        tasks_dir = tmp_path / "tasks"
        sid = "abc-session"
        (projects_dir / "proj").mkdir(parents=True)
        (projects_dir / "proj" / f"{sid}.jsonl").write_text("{}\n")
        (tasks_dir / sid).mkdir(parents=True)
        (tasks_dir / sid / "1.json").write_text('{"subject":"do it","status":"pending"}')
        (tasks_dir / "orphan-session").mkdir()
        (tasks_dir / "orphan-session" / "1.json").write_text('{"subject":"x","status":"pending"}')

        with (
            patch("asm.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("asm.services.claude_data.TASKS_DIR", tasks_dir),
        ):
            todos = get_todos()

        names = {t.name: t for t in todos}
        assert sid in names and not names[sid].is_orphaned
        assert names["orphan-session"].is_orphaned

    def test_find_duplicate_sessions(self, tmp_path: Path):
        from asm.services.claude_data import find_duplicate_sessions

        projects_dir = tmp_path / "projects"
        a = projects_dir / "proj-a"
        b = projects_dir / "proj-b"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        (a / "dup.jsonl").write_text("{}\n")
        (b / "dup.jsonl").write_text("{}\n")
        (a / "unique.jsonl").write_text("{}\n")

        with patch("asm.services.claude_data.PROJECTS_DIR", projects_dir):
            dups = find_duplicate_sessions()

        assert set(dups.keys()) == {"dup"}
        assert sorted(dups["dup"]) == ["proj-a", "proj-b"]


class TestPricing:
    def test_new_opus_models_use_cheap_tier(self):
        from asm.services.pricing import calc_cost, is_billable

        usage = {"input_tokens": 1_000_000}
        # opus 4.5+ -> $5/M input; legacy opus 4.1 -> $15/M
        assert calc_cost(usage, "claude-opus-4-8") == 5.0
        assert calc_cost(usage, "claude-opus-4-7-20260416") == 5.0
        assert calc_cost(usage, "claude-opus-4-1") == 15.0
        # Unknown future opus defaults to current (cheap) pricing.
        assert calc_cost(usage, "claude-opus-9-0") == 5.0
        assert is_billable("claude-opus-4-8")
        assert not is_billable("<synthetic>")

    def test_claude5_family_rates(self):
        from asm.services.pricing import calc_cost, display_model

        inp = {"input_tokens": 1_000_000}
        assert calc_cost(inp, "claude-fable-5") == 10.0
        assert calc_cost(inp, "claude-fable-5-20260601") == 10.0
        assert calc_cost(inp, "claude-mythos-5") == 10.0
        assert calc_cost(inp, "claude-sonnet-5") == 2.0
        # Unknown future fable/mythos falls to the fable tier, not sonnet.
        assert calc_cost(inp, "claude-fable-6") == 10.0
        out = {"output_tokens": 1_000_000}
        assert calc_cost(out, "claude-fable-5") == 50.0
        cache = {"cache_read_input_tokens": 1_000_000}
        assert calc_cost(cache, "claude-fable-5") == 1.0
        # Display names strip date suffixes so model tables stay uniform.
        assert display_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
        assert display_model("claude-opus-4-6[1m]") == "claude-opus-4-6"
