# cc-session-utils

<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Claude_AI_logo.svg" alt="Claude" width="60"/>

### Terminal UI for Managing Claude Code Sessions

**Dashboard, session cleanup, migration, backup/restore — all in your terminal**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS-1A1915?style=for-the-badge)](#)

**[한국어](README.ko.md)**

</div>

---

## Why?

The more you use Claude Code, the more files pile up in `~/.claude` — session data, cost logs, debug files, file history snapshots. It becomes hard to track which projects cost how much, or which files are orphaned and safe to clean up.

**cc-session-utils** gives you a visual dashboard right in your terminal to manage all of it.

---

## Demo

<!-- Record each GIF with: asciinema rec demo.cast && agg demo.cast demo.gif -->
<!-- Recommended: 10-15 seconds per GIF, 80x24 terminal size -->

| Feature | Preview |
|:--------|:--------|
| **Dashboard** — Cost & usage stats | ![Dashboard](docs/demo-dashboard.gif) |
| **Projects** — Session tree & preview | ![Projects](docs/demo-projects.gif) |
| **Migrate** — Select & move sessions | ![Migrate](docs/demo-migrate.gif) |
| **Backups** — Backup & restore | ![Backups](docs/demo-backups.gif) |

> GIFs coming soon. To record: `pip install asciinema agg`, then `asciinema rec` + `agg`.

---

## Features

### Dashboard
- Total cost and per-model (Opus / Sonnet / Haiku) token/cost breakdown
- Daily / weekly / monthly usage table (click to switch)
- Project cost Top 10 (bar chart)
- Data overview: session count, file history, debug/todo files, disk usage

### Project Management
- Tree view of all projects from `.claude.json`
- Expand projects to see sessions, click to preview conversations
- Visual distinction for missing projects (folder deleted/moved)
- Trash individual sessions, remove projects from config
- Detect and bulk-clean orphaned session directories
- `--path` option to filter to a specific project

### File History
- Manage Claude's file version snapshots
- Detect and bulk-clean orphaned entries

### Debug / Todos
- Manage Claude Code internal debug logs and todo memos
- Right-side preview panel for file content
- Bulk-clean empty files (`[]`, `{}`, or blank)
- Bulk-clean orphaned files

### Session Migration
- Copy sessions from Project A to Project B (originals preserved)
- **Per-session selection:** `Space` to check/uncheck, `Enter` to preview conversation
- Append mode (keep existing, skip duplicates) or Overwrite mode
- Memory files and session index migrated together
- Path references (`cwd`, `projectPath`, etc.) auto-updated

### Backup / Restore
- Config backup: just `.claude.json`
- Full backup: entire `~/.claude` directory
- List, restore (auto-creates safety backup first), delete
- Backup deletion goes to OS trash (`send2trash`)
- Restore failure auto-rollback (rename+rollback pattern)

### Safety
- **Symlink rejection:** Refuses to operate on symbolic links
- **Path validation:** `is_relative_to` allowlist blocks access outside `~/.claude`
- **Thread-safe trash log:** All deletions recorded in `~/.cc-tui/trash-log.jsonl` with `threading.Lock`
- **Safe deletion:** Everything goes to OS trash via `send2trash` — no permanent deletes
- **Atomic config writes:** `.claude.json` updates via tempfile + `os.replace`

---

## Install

### From PyPI (recommended)

```bash
pip install cc-session-utils
```

### With uv

```bash
uv tool install cc-session-utils
```

<details>
<summary><strong>From source (development)</strong></summary>

```bash
git clone https://github.com/Bae-ChangHyun/cc-session-utils.git
cd cc-session-utils
uv sync
uv run cc-tui
```

</details>

---

## Usage

```bash
cc-tui                          # Launch TUI
cc-tui --path /your/project     # Filter to specific project
cc-tui --lang ko                # Korean UI
CC_TUI_LANG=ko cc-tui           # Via env var
```

### Keyboard Shortcuts

| Key | Action |
|:---:|:---|
| `F1`–`F6` | Switch tabs (Dashboard → Backups) |
| `q` | Quit |
| `r` | Refresh all data |
| `↑`/`↓` | Navigate lists |
| `d` | Trash selected item |
| `D` | Trash all orphaned |
| `Space` | Toggle selection |
| `Enter` | Preview session conversation (Migrate tab) |

---

## Architecture

```
src/cc_tui/
├── __main__.py          # CLI entry (--path, --lang)
├── app.py               # Textual app, tab layout
├── i18n.py              # i18n (English / Korean)
├── models.py            # Data models, path constants
├── utils.py             # Shared utilities
├── screens/
│   ├── dashboard.py     # Usage & cost stats
│   ├── projects.py      # Project/session tree
│   ├── file_history.py  # File history management
│   ├── debug_todos.py   # Debug/todo file management
│   ├── migrate.py       # Session migration + preview
│   ├── backups.py       # Backup & restore
│   └── confirm.py       # Confirmation dialog
├── services/
│   ├── claude_data.py   # Claude data parsing
│   ├── backup.py        # Backup/restore logic
│   ├── cleaner.py       # Trash operations + path validation
│   └── migrate.py       # Migration logic
└── widgets/
    └── action_bar.py    # Reusable action bar widget
```

---

## Data Paths

| Path | Description |
|:---|:---|
| `~/.claude.json` | Project list, costs, model usage |
| `~/.claude/projects/` | Per-project session JSONL files |
| `~/.claude/file-history/` | File version snapshots |
| `~/.claude/debug/` | Internal debug logs |
| `~/.claude/todos/` | Internal todo memos |
| `~/.cc-tui/backups/` | Backups created by cc-tui |
| `~/.cc-tui/trash-log.jsonl` | Deletion audit log |

---

## Tech Stack

| Tech | Role |
|:---|:---|
| [Python 3.11+](https://python.org) | Language |
| [Textual](https://github.com/Textualize/textual) | TUI framework |
| [Rich](https://github.com/Textualize/rich) | Text formatting (built into Textual) |
| [send2trash](https://github.com/arsenetar/send2trash) | OS trash integration |
| [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) | Session data (fallback: JSONL parsing) |

---

## Contributing

Bug reports, feature requests, and pull requests are welcome.

```bash
git clone https://github.com/Bae-ChangHyun/cc-session-utils.git
cd cc-session-utils
uv sync
uv run cc-tui
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">

Made with **Claude Code**

</div>
