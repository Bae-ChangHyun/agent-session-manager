"""Entry point for cc-tui."""

import argparse

from cc_tui.app import CCTuiApp


def main():
    parser = argparse.ArgumentParser(description="CC-TUI: Claude Code Session Manager")
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Specific project path to manage (default: global ~/.claude)",
    )
    args = parser.parse_args()

    app = CCTuiApp(target_path=args.path)
    app.run()


if __name__ == "__main__":
    main()
