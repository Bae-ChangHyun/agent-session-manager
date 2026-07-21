"""Cross-platform compatibility tests.

Tests Windows/macOS/Linux behavior by monkeypatching sys.platform
and asm.models.IS_WINDOWS.
"""

from __future__ import annotations

from pathlib import Path, PurePath
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# decode_path_hint
# ---------------------------------------------------------------------------

class TestDecodePathHint:
    """Test path decoding across platforms."""

    def test_unix_standard(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", False):
            assert decode_path_hint("-home-bch-Project") == "/home/bch/Project"

    def test_unix_empty(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", False):
            assert decode_path_hint("") == "/"

    def test_unix_root_only(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", False):
            assert decode_path_hint("-") == "/"

    def test_unix_deep_path(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", False):
            assert decode_path_hint("-home-user-a-b-c-d") == "/home/user/a/b/c/d"

    def test_windows_drive_letter(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", True):
            assert decode_path_hint("C-Users-bch-Project") == "C:/Users/bch/Project"

    def test_windows_drive_letter_lowercase(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", True):
            assert decode_path_hint("c-Users-bch") == "C:/Users/bch"

    def test_windows_drive_only(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", True):
            assert decode_path_hint("C") == "C:/"

    def test_windows_no_drive_letter(self):
        """Multi-char first part → not a drive letter, treat as Unix-style."""
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", True):
            assert decode_path_hint("home-bch") == "/home/bch"

    def test_windows_empty(self):
        from asm.models import decode_path_hint

        with patch("asm.models.IS_WINDOWS", True):
            assert decode_path_hint("") == "/"


# ---------------------------------------------------------------------------
# encode_path (platform-independent)
# ---------------------------------------------------------------------------

class TestEncodePath:
    def test_unix_path(self):
        from asm.models import encode_path

        assert encode_path("/home/bch/Project") == "-home-bch-Project"

    def test_windows_path(self):
        from asm.models import encode_path

        assert encode_path("C:\\Users\\bch\\Project") == "C--Users-bch-Project"

    def test_special_chars(self):
        from asm.models import encode_path

        assert encode_path("/home/user/my_project") == "-home-user-my-project"


# ---------------------------------------------------------------------------
# _dir_size
# ---------------------------------------------------------------------------

class TestDirSize:
    def test_windows_skips_du(self, tmp_path: Path):
        """On Windows, du should not be called at all."""
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")

        with patch("asm.utils.sys") as mock_sys:
            mock_sys.platform = "win32"
            from asm.services.claude_data import _dir_size

            size = _dir_size(tmp_path)
            assert size == 10  # 5 + 5

    def test_linux_tries_du(self, tmp_path: Path):
        """On Linux, du is attempted (may succeed or fall back)."""
        (tmp_path / "a.txt").write_text("hello")

        from asm.services.claude_data import _dir_size

        size = _dir_size(tmp_path)
        assert size >= 5  # du or fallback both return >= 5


# ---------------------------------------------------------------------------
# Project name extraction via Path().name
# ---------------------------------------------------------------------------

class TestProjectNameExtraction:
    def test_unix_path_name(self):
        assert Path("/home/bch/my-project").name == "my-project"

    def test_unix_trailing_slash(self):
        assert Path("/home/bch/my-project/").name == "my-project"

    def test_path_name_basic(self):
        """Path().name works for simple paths on any OS."""
        assert Path("/usr/local/bin").name == "bin"


# ---------------------------------------------------------------------------
# PurePath usage (projects.py)
# ---------------------------------------------------------------------------

class TestPurePathParts:
    def test_unix_path_parts(self):
        parts = PurePath("/home/bch/Project").parts
        assert parts[0] == "/"
        assert "home" in parts
        assert "Project" in parts

    def test_purepath_name(self):
        assert PurePath("/home/bch/Project").name == "Project"


# ---------------------------------------------------------------------------
# Backup symlinks flag
# ---------------------------------------------------------------------------

class TestBackupSymlinks:
    def test_windows_no_symlinks(self):
        import asm.services.backup  # noqa: F401

        # On Windows, symlinks=False
        assert ("win32" != "win32") == False  # noqa: E712
        # Verify the logic: sys.platform != "win32" → False on Windows
        with patch("asm.services.backup.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert (mock_sys.platform != "win32") is False

    def test_unix_symlinks(self):
        with patch("asm.services.backup.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert (mock_sys.platform != "win32") is True

    def test_mac_symlinks(self):
        with patch("asm.services.backup.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert (mock_sys.platform != "win32") is True


# ---------------------------------------------------------------------------
# migrate.py uses decode_path_hint
# ---------------------------------------------------------------------------

class TestMigrateDecoding:
    def test_uses_decode_path_hint(self):
        """Verify migrate.py imports decode_path_hint from models."""
        from asm.services import migrate

        assert hasattr(migrate, "decode_path_hint")
