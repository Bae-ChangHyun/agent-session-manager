"""Entry point for agentkeep."""

import argparse

from agentkeep.app import CCTuiApp
from agentkeep.i18n import init_lang
from agentkeep.models import migrate_legacy_data_dir


def main():
    parser = argparse.ArgumentParser(
        prog="agentkeep",
        description="agentkeep: manage Claude Code & Codex sessions, cost and data",
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
        help="UI language (default: en, or set CC_TUI_LANG env var)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        choices=["all", "claude", "codex"],
        help="Initial dashboard source filter: all (default), claude, or codex. "
             "Both sources are always shown; toggle in-app with 's'.",
    )
    args = parser.parse_args()

    init_lang(args.lang)
    migrate_legacy_data_dir()

    app = CCTuiApp(target_path=args.path, source=args.source)
    app.run()


if __name__ == "__main__":
    main()
