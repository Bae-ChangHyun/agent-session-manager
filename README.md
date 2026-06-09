<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.simpleicons.org/anthropic/D97757">
  <source media="(prefers-color-scheme: light)" srcset="https://cdn.simpleicons.org/anthropic/1A1915">
  <img alt="asm" width="48" height="48">
</picture>

# agent-session-manager

**Manage your Claude Code & Codex sessions, cost, and data — all in your terminal**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-1A1915?style=for-the-badge)](#)

Combined cost dashboard · Session cleanup · Migration · Backup/Restore

**[한국어](README.ko.md)**

</div>

---

## Demo

<div align="center">
<img src="docs/demo.gif" alt="asm" width="800"/>
</div>

---

## Why?

The more you use **Claude Code** and **OpenAI Codex**, the more files pile up in `~/.claude` and `~/.codex` — session data, cost logs, debug files, snapshots. It gets hard to track which projects cost how much, or which files are orphaned and safe to clean up.

**agent-session-manager** gives you one visual dashboard in your terminal to manage both — with a Claude / Codex filter so you can see them combined or separately.

---

## Features

### 📊 Combined Dashboard
- Total cost across **both Claude and Codex**, with a source filter (`s` → All / Claude / Codex)
- Per-model token/cost breakdown (Opus / Sonnet / Haiku / GPT-5.x), tagged by source
- Daily / weekly / monthly usage table
- Project cost Top 10 (Claude projects + Codex working dirs)
- Accurate, up-to-date model pricing (LiteLLM-sourced rate table)

### 📁 Claude Project Management
- Tree view of all projects from `.claude.json`
- Expand to see sessions, click to preview conversations
- Trash sessions, remove projects from config
- Detect and bulk-clean orphaned sessions
- **Duplicate sessions:** find the same session copied across projects and delete individual copies

### 🤖 Codex Sessions
- Browse `~/.codex` rollout sessions grouped by working directory
- Preview conversations, trash individual sessions

### 📋 File History · 🐛 Debug / Todos
- Manage Claude's file snapshots, debug logs, and per-session task lists (`tasks/`)
- Bulk-clean empty and orphaned entries

### 🔄 Session Migration (Claude)
- Copy sessions between projects (originals preserved), append or overwrite
- Path references auto-updated after migration

### 💾 Backup / Restore
- Claude: config / settings / plugins / sessions / full backup
- Codex: session backup (`~/.codex/sessions`, excludes large caches)
- Auto safety-backup before restore, failure auto-rollback, recovery snapshots

---

## Install

```bash
# pip
pip install agent-session-manager

# uv
uv tool install agent-session-manager

# From source
git clone https://github.com/Bae-ChangHyun/agent-session-manager.git
cd agent-session-manager
uv sync && uv run asm
```

---

## Usage

```bash
asm                       # Launch (shows Claude + Codex together)
asm --source codex        # Start with the dashboard filtered to Codex
asm --path /your/project  # Filter to a specific Claude project
asm --lang ko             # Korean UI
```

Both sources are always available in one session — the `--source` flag only sets
the dashboard's initial filter, which you can change anytime with `s`.

### Keyboard Shortcuts

| Key | Action |
|:---:|:---|
| `F1`–`F6` | Switch tabs |
| `s` | Dashboard source filter (All / Claude / Codex) |
| `Tab` / `Shift+Tab` | Cycle dashboard period (Daily / Weekly / Monthly) |
| `1` / `2` / `3` | Switch dashboard period directly |
| `q` | Quit · `r` Refresh all |
| `d` / `D` | Trash selected / all orphaned |
| `Space` | Toggle selection · `Enter` Preview conversation (Migrate) |

---

## Data Paths

| Path | Description |
|:---|:---|
| `~/.claude.json` · `~/.claude/projects/` | Claude project list, costs, session JSONL |
| `~/.claude/file-history/` · `~/.claude/debug/` · `~/.claude/tasks/` | Snapshots, debug logs, task lists |
| `~/.codex/sessions/` | Codex rollout session files |
| `~/.asm/backups/` | Backups (migrated automatically from the old `~/.cc-tui`) |
| `~/.asm/trash-log.jsonl` | Deletion audit log |

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
