"""Tests for the startup update check."""

from __future__ import annotations

from asm.services import update


class TestVersionCompare:
    def test_is_newer(self):
        assert update.is_newer("0.7.0", "0.6.0")
        assert update.is_newer("0.6.1", "0.6.0")
        assert update.is_newer("1.0.0", "0.9.9")
        assert not update.is_newer("0.6.0", "0.6.0")
        assert not update.is_newer("0.5.0", "0.6.0")

    def test_current_version_installed(self):
        # Running the suite means the package is importable/installed.
        assert update.current_version() is not None

    def test_upgrade_command_targets_dist(self):
        cmd = update._upgrade_command()
        assert update.DIST_NAME in cmd
        assert cmd[:3] in (["uv", "tool", "upgrade"],) or cmd[1:4] == ["-m", "pip", "install"]


class TestPromptFlow:
    def _force_tty(self, monkeypatch):
        monkeypatch.setattr(update.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(update.sys.stdout, "isatty", lambda: True)

    def test_no_update_when_same_version(self, monkeypatch, capsys):
        self._force_tty(monkeypatch)
        monkeypatch.setattr(update, "current_version", lambda: "0.6.0")
        monkeypatch.setattr(update, "latest_version", lambda timeout=2.5: "0.6.0")
        called = []
        monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: called.append(a))
        update.maybe_prompt_update()
        assert not called  # no prompt, no upgrade

    def test_declined_update_does_not_upgrade(self, monkeypatch):
        self._force_tty(monkeypatch)
        monkeypatch.setattr(update, "current_version", lambda: "0.6.0")
        monkeypatch.setattr(update, "latest_version", lambda timeout=2.5: "0.7.0")
        monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
        called = []
        monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: called.append(a))
        update.maybe_prompt_update()
        assert not called

    def test_accepted_update_runs_command(self, monkeypatch):
        self._force_tty(monkeypatch)
        monkeypatch.setattr(update, "current_version", lambda: "0.6.0")
        monkeypatch.setattr(update, "latest_version", lambda timeout=2.5: "0.7.0")
        monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

        class _R:
            returncode = 0

        ran = {}

        def _run(cmd, *a, **k):
            ran["cmd"] = cmd
            return _R()

        monkeypatch.setattr(update.subprocess, "run", _run)
        # On success it exits; capture that.
        import pytest
        with pytest.raises(SystemExit):
            update.maybe_prompt_update()
        assert update.DIST_NAME in ran["cmd"]

    def test_skips_when_not_tty(self, monkeypatch):
        monkeypatch.setattr(update.sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(update, "latest_version", lambda timeout=2.5: "9.9.9")
        called = []
        monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: called.append(a))
        update.maybe_prompt_update()
        assert not called
