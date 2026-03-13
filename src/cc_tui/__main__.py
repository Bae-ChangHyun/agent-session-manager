"""Entry point for cc-tui."""

import argparse

from cc_tui.app import CCTuiApp
from cc_tui.i18n import init_lang


def main():
    parser = argparse.ArgumentParser(description="CC-TUI: Claude Code Session Manager")
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
    args = parser.parse_args()

    init_lang(args.lang)

    app = CCTuiApp(target_path=args.path)
    app.run()


if __name__ == "__main__":
    main()
