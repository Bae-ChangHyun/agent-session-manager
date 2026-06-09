"""Startup update check.

On launch we ask PyPI whether a newer release exists and, if so, offer a
``y/N`` prompt to upgrade in place. Everything here fails quietly (offline,
timeouts, source checkouts) so it never blocks starting the app.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request

# PyPI distribution name (the import package is `asm`). Change this one constant
# if the project is renamed.
DIST_NAME = "agent-session-manager"

_PYPI_URL = f"https://pypi.org/pypi/{DIST_NAME}/json"
_SKIP_ENV = "ASM_NO_UPDATE_CHECK"


def current_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version(DIST_NAME)
        except PackageNotFoundError:
            return None
    except Exception:
        return None


def latest_version(timeout: float = 2.5) -> str | None:
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("info", {}).get("version")
    except Exception:
        return None


def _parse(v: str) -> tuple:
    try:
        from packaging.version import Version
        return (Version(v),)
    except Exception:
        import re
        parts = []
        for chunk in re.split(r"[.\-+]", v):
            digits = "".join(c for c in chunk if c.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    try:
        return _parse(latest) > _parse(current)
    except Exception:
        return False


def _upgrade_command() -> list[str]:
    """Best-effort upgrade command for how the tool was installed."""
    # uv tool installs live outside site-packages; prefer `uv tool upgrade`.
    exe = (sys.argv[0] or "").lower()
    looks_like_uv_tool = "uv/tools" in sys.prefix.replace("\\", "/") or "/tools/" in exe
    if shutil.which("uv") and (looks_like_uv_tool or "uv" in sys.prefix.lower()):
        return ["uv", "tool", "upgrade", DIST_NAME]
    return [sys.executable, "-m", "pip", "install", "--upgrade", DIST_NAME]


def maybe_prompt_update() -> None:
    """Check for a newer release and offer to upgrade. No-op when not applicable."""
    if os.environ.get(_SKIP_ENV):
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return  # don't prompt in pipes / CI
    current = current_version()
    if not current:
        return  # running from a source checkout, nothing to upgrade
    latest = latest_version()
    if not latest or not is_newer(latest, current):
        return

    print(f"\n  {DIST_NAME}: update available  {current} → \033[1m{latest}\033[0m")
    try:
        answer = input("  Update now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if answer not in ("y", "yes"):
        return

    cmd = _upgrade_command()
    print(f"  Running: {' '.join(cmd)}\n")
    try:
        result = subprocess.run(cmd)
    except OSError as e:
        print(f"  Update failed to start: {e}")
        return
    if result.returncode == 0:
        print(f"\n  Updated to {latest}. Restart `{DIST_NAME}` to use the new version.")
        sys.exit(0)
    print("\n  Update command failed; continuing with the current version.")
