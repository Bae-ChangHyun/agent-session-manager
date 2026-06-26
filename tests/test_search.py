"""Tests for full-text session body search."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import asm.models as models
from asm.services import search


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    projects = tmp_path / "projects" / "-home-bch-test"
    projects.mkdir(parents=True)
    # 'warp 한글' appears only mid-conversation, never in the first message,
    # so a title-only search would miss it but a body search must find it.
    (projects / "aaaa-1111.jsonl").write_text(
        '{"type":"user","message":{"content":"첫 질문입니다"}}\n'
        '{"type":"assistant","message":{"content":"warp 한글 패치 얘기"}}\n',
        encoding="utf-8",
    )
    (projects / "bbbb-2222.jsonl").write_text(
        '{"type":"user","message":{"content":"전혀 관련 없는 세션"}}\n',
        encoding="utf-8",
    )
    codex = tmp_path / "codex-sessions" / "2026" / "06" / "26"
    codex.mkdir(parents=True)
    (codex / "rollout-2026-06-26T10-00-00-cccc.jsonl").write_text(
        '{"type":"session_meta","payload":{"id":"cccc"}}\n'
        '{"payload":{"content":[{"type":"text","text":"warp terminal 한글"}]}}\n',
        encoding="utf-8",
    )
    return tmp_path / "projects", tmp_path / "codex-sessions"


def test_claude_body_search_finds_mid_conversation(tmp_path):
    projects_dir, codex_dir = _setup(tmp_path)
    with patch.object(models, "PROJECTS_DIR", projects_dir), \
         patch.object(models, "CODEX_SESSIONS_DIR", codex_dir):
        importlib.reload(search)
        assert search.search_claude_session_ids("warp") == {"aaaa-1111"}
        # Korean term living only in the body is still matched.
        assert search.search_claude_session_ids("한글 패치") == {"aaaa-1111"}
        # Non-matching query returns nothing.
        assert search.search_claude_session_ids("존재하지않는단어") == set()
    importlib.reload(search)


def test_search_ignores_whitespace(tmp_path):
    """Body has 'warp 한글'; both spaced and unspaced queries find it."""
    projects_dir, codex_dir = _setup(tmp_path)
    with patch.object(models, "PROJECTS_DIR", projects_dir), \
         patch.object(models, "CODEX_SESSIONS_DIR", codex_dir):
        importlib.reload(search)
        spaced = search.search_claude_session_ids("warp 한글")
        unspaced = search.search_claude_session_ids("warp한글")
        assert spaced == unspaced == {"aaaa-1111"}
        # Same for the Python fallback (ripgrep forced off).
        with patch("asm.services.search.shutil.which", return_value=None):
            assert search.search_claude_session_ids("warp한글") == {"aaaa-1111"}
    importlib.reload(search)


def test_normalize():
    assert search.normalize("Warp 한글") == search.normalize("warp한글")
    assert search.normalize("  A  B ") == "ab"


def test_codex_body_search_returns_rollout_path(tmp_path):
    projects_dir, codex_dir = _setup(tmp_path)
    with patch.object(models, "PROJECTS_DIR", projects_dir), \
         patch.object(models, "CODEX_SESSIONS_DIR", codex_dir):
        importlib.reload(search)
        paths = search.search_codex_rollout_paths("한글")
        assert len(paths) == 1
        assert Path(next(iter(paths))).name == "rollout-2026-06-26T10-00-00-cccc.jsonl"
    importlib.reload(search)


def test_blank_query_is_empty(tmp_path):
    projects_dir, codex_dir = _setup(tmp_path)
    with patch.object(models, "PROJECTS_DIR", projects_dir), \
         patch.object(models, "CODEX_SESSIONS_DIR", codex_dir):
        importlib.reload(search)
        assert search.search_claude_session_ids("   ") == set()
        assert search.search_codex_rollout_paths("") == set()
    importlib.reload(search)


def test_python_fallback_matches_ripgrep(tmp_path):
    """With ripgrep forced unavailable, the Python scan finds the same hits."""
    projects_dir, codex_dir = _setup(tmp_path)
    with patch.object(models, "PROJECTS_DIR", projects_dir), \
         patch.object(models, "CODEX_SESSIONS_DIR", codex_dir), \
         patch("asm.services.search.shutil.which", return_value=None):
        importlib.reload(search)
        assert search.search_claude_session_ids("warp") == {"aaaa-1111"}
        assert len(search.search_codex_rollout_paths("한글")) == 1
    importlib.reload(search)
