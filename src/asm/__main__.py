"""Entry point for asm."""

import argparse

from asm.app import CCTuiApp
from asm.i18n import init_lang
from asm.models import migrate_legacy_data_dir
from asm.services.update import maybe_prompt_update


def main():
    parser = argparse.ArgumentParser(
        prog="asm",
        description="asm: manage Claude Code & Codex sessions, cost and data",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Specific project path to manage (default: global ~/.claude)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        choices=["en", "ko"],
        help="UI language (default: en, or set ASM_LANG env var)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        choices=["all", "claude", "codex"],
        help="Initial dashboard source filter: all (default), claude, or codex. "
             "Both sources are always shown; toggle in-app with 's'.",
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Skip the startup check for a newer release.",
    )
    args = parser.parse_args()

    init_lang(args.lang)
    migrate_legacy_data_dir()
    if not args.no_update_check:
        maybe_prompt_update()

    app = CCTuiApp(target_path=args.path, source=args.source)
    app.run()


if __name__ == "__main__":
    main()
