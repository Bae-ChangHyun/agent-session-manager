<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.simpleicons.org/anthropic/D97757">
  <source media="(prefers-color-scheme: light)" srcset="https://cdn.simpleicons.org/anthropic/1A1915">
  <img alt="Claude" width="48" height="48">
</picture>

# cc-session-utils

**Terminal UI for Managing Claude Code Sessions**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-1A1915?style=for-the-badge)](#)

Dashboard · Session cleanup · Migration · Backup/Restore — all in your terminal

**[한국어](README.ko.md)**

</div>

---

## Demo

<div align="center">
<img src="docs/demo.gif" alt="cc-session-utils demo" width="800"/>
</div>

---

## Why?

The more you use Claude Code, the more files pile up in `~/.claude` — session data, cost logs, debug files, file history snapshots. It becomes hard to track which projects cost how much, or which files are orphaned and safe to clean up.

**cc-session-utils** gives you a visual dashboard right in your terminal to manage all of it.

---

## Features

### 📊 Dashboard
- Total cost and per-model (Opus / Sonnet / Haiku) token/cost breakdown
- Daily / weekly / monthly usage table
- Project cost Top 10 bar chart
- Data overview: sessions, file history, debug/todo files, disk usage

### 📁 Project Management
- Tree view of all projects from `.claude.json`
- Expand to see sessions, click to preview conversations
- Trash sessions, remove projects from config
- Detect and bulk-clean orphaned sessions
- `--path` option to filter to a specific project

### 📋 File History
- Manage Claude's file version snapshots
- Detect and bulk-clean orphaned entries

### 🐛 Debug / Todos
- Manage debug logs and todo memos with preview panel
- Bulk-clean empty and orphaned files

### 🔄 Session Migration
- Copy sessions between projects (originals preserved)
- **Per-session selection:** `Space` to check/uncheck, `Enter` to preview conversation
- Append or Overwrite mode
- Path references auto-updated after migration

### 💾 Backup / Restore
- Config backup (`.claude.json`) or full backup (`~/.claude`)
- Auto safety-backup before restore
- Restore failure auto-rollback

---

## Install

```bash
# pip
pip install cc-session-utils

# uv
uv tool install cc-session-utils

# From source
git clone https://github.com/Bae-ChangHyun/cc-session-utils.git
cd cc-session-utils
uv sync && uv run cc-tui
```

Both `cc-tui` and `cc-session-utils` are installed as launch commands and start the same app.

---

## Usage

```bash
cc-tui                          # Launch
cc-session-utils                # Same app, alternate command name
cc-tui --path /your/project     # Filter to project
cc-tui --lang ko                # Korean UI
```

### Keyboard Shortcuts

| Key | Action |
|:---:|:---|
| `F1`–`F6` | Switch tabs |
| `Tab` / `Shift+Tab` | Cycle dashboard period (Daily / Weekly / Monthly) |
| `1` / `2` / `3` | Switch dashboard period directly |
| `q` | Quit |
| `r` | Refresh all |
| `d` / `D` | Trash selected / all orphaned |
| `Space` | Toggle selection |
| `Enter` | Preview conversation (Migrate) |

---

## Data Paths

| Path | Description |
|:---|:---|
| `~/.claude.json` | Project list, costs, model usage |
| `~/.claude/projects/` | Session JSONL files |
| `~/.claude/file-history/` | File version snapshots |
| `~/.claude/debug/` | Debug logs |
| `~/.claude/todos/` | Todo memos |
| `~/.cc-tui/backups/` | Backups |
| `~/.cc-tui/trash-log.jsonl` | Deletion audit log |

---

## Tech Stack

[Python 3.11+](https://python.org) · [Textual](https://github.com/Textualize/textual) · [Rich](https://github.com/Textualize/rich) · [send2trash](https://github.com/arsenetar/send2trash) · [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/)

---

## License

[MIT](LICENSE)

<div align="center">
<br/>
Made with <b>Claude Code</b>
</div>
