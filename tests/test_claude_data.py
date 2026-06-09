"""Tests for Claude data service behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agentkeep.services.claude_data import get_session_messages, get_session_to_project_map


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

        with patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir):
            messages = get_session_messages(session_id, project_dir="proj-right", limit=10)

        assert messages == [{"type": "user", "content": "right project"}]


class TestSessionProjectMap:
    def test_get_session_to_project_map_marks_ambiguous_encoded_dirs(self, tmp_path: Path):
        projects_dir = tmp_path / "projects"
        encoded_dir = projects_dir / "-tmp-demo-app"
        encoded_dir.mkdir(parents=True)
        (encoded_dir / "session-1.jsonl").write_text("{}\n")

        fake_paths = {"/tmp/demo-app", "/tmp/demo_app"}

        with (
            patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("agentkeep.services.claude_data.get_project_paths", return_value=fake_paths),
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
        from agentkeep.services.claude_data import _resolve_project_dir
        from agentkeep.models import encode_path

        projects_dir = tmp_path / "projects"
        abs_path = "/work/my-proj"
        encoded = projects_dir / encode_path(abs_path)
        encoded.mkdir(parents=True)

        with patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir):
            resolved = _resolve_project_dir(abs_path)

        assert resolved is not None
        assert resolved.parent == projects_dir

    def test_get_project_sessions_uses_index_and_jsonl(self, tmp_path: Path):
        from agentkeep.services.claude_data import get_project_sessions
        from agentkeep.models import encode_path
        import json

        projects_dir = tmp_path / "projects"
        abs_path = "/work/web-app"
        d = projects_dir / encode_path(abs_path)
        d.mkdir(parents=True)
        sid = "11111111-2222-3333-4444-555555555555"
        (d / f"{sid}.jsonl").write_text('{"type":"user","message":{"content":"hi"}}\n')
        (d / "sessions-index.json").write_text(json.dumps({
            "version": 1,
            "entries": [{"sessionId": sid, "summary": "indexed summary", "gitBranch": "main"}],
        }))

        with patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir):
            sessions = get_project_sessions(abs_path)

        assert len(sessions) == 1
        assert sessions[0].summary == "indexed summary"
        assert sessions[0].git_branch == "main"
        assert sessions[0].file_size > 0

    def test_get_todos_reads_tasks_dir(self, tmp_path: Path):
        from agentkeep.services.claude_data import get_todos

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
            patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("agentkeep.services.claude_data.TASKS_DIR", tasks_dir),
        ):
            todos = get_todos()

        names = {t.name: t for t in todos}
        assert sid in names and not names[sid].is_orphaned
        assert names["orphan-session"].is_orphaned

    def test_find_duplicate_sessions(self, tmp_path: Path):
        from agentkeep.services.claude_data import find_duplicate_sessions

        projects_dir = tmp_path / "projects"
        a = projects_dir / "proj-a"
        b = projects_dir / "proj-b"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        (a / "dup.jsonl").write_text("{}\n")
        (b / "dup.jsonl").write_text("{}\n")
        (a / "unique.jsonl").write_text("{}\n")

        with patch("agentkeep.services.claude_data.PROJECTS_DIR", projects_dir):
            dups = find_duplicate_sessions()

        assert set(dups.keys()) == {"dup"}
        assert sorted(dups["dup"]) == ["proj-a", "proj-b"]


class TestPricing:
    def test_new_opus_models_use_cheap_tier(self):
        from agentkeep.services.pricing import calc_cost, is_billable

        usage = {"input_tokens": 1_000_000}
        # opus 4.5+ -> $5/M input; legacy opus 4.1 -> $15/M
        assert calc_cost(usage, "claude-opus-4-8") == 5.0
        assert calc_cost(usage, "claude-opus-4-7-20260416") == 5.0
        assert calc_cost(usage, "claude-opus-4-1") == 15.0
        # Unknown future opus defaults to current (cheap) pricing.
        assert calc_cost(usage, "claude-opus-9-0") == 5.0
        assert is_billable("claude-opus-4-8")
        assert not is_billable("<synthetic>")
