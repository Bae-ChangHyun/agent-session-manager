"""Tests for Claude data service behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cc_tui.services.claude_data import get_session_messages, get_session_to_project_map


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

        with patch("cc_tui.services.claude_data.PROJECTS_DIR", projects_dir):
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
            patch("cc_tui.services.claude_data.PROJECTS_DIR", projects_dir),
            patch("cc_tui.services.claude_data.get_project_paths", return_value=fake_paths),
        ):
            mapping = get_session_to_project_map()

        assert mapping["session-1"].startswith("[ambiguous] ")
        assert "/tmp/demo-app" in mapping["session-1"]
        assert "/tmp/demo_app" in mapping["session-1"]
