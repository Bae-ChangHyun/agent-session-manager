<div align="center">

# agent-session-manager

**One terminal dashboard for everything Claude Code and Codex leave behind.**
See cost, browse sessions, and clean up `~/.claude` and `~/.codex` — side by side, with a Claude / Codex filter.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Built with Textual](https://img.shields.io/badge/Built%20with-Textual-5A2CA0?style=flat-square)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-orange?style=flat-square)](#)
[![Status](https://img.shields.io/badge/Status-Personal--use-lightgrey?style=flat-square)](#)

`asm` · **[한국어](README.ko.md)**

</div>

---

> **⚠️ Heads up**
> This is a personal tool that reads and edits the **internal data of Claude Code and OpenAI Codex** (`~/.claude`, `~/.codex`). Every delete goes to the OS trash and is logged, but you should still back up before bulk operations. Not affiliated with Anthropic or OpenAI.

---

## What it is

If you live in **Claude Code** and **Codex**, the two of them quietly fill `~/.claude` and `~/.codex` with session transcripts, cost logs, debug files, task lists, and snapshots. After a few weeks it's impossible to tell which projects burned the most tokens, or which files are orphaned and safe to delete.

**agent-session-manager** (`asm`) puts all of it in one terminal dashboard. Both agents show up together, and a single keystroke filters the view to **All / Claude / Codex** so you can compare spend or drill into one tool.

### 💡 Why it exists

- **Problem:** cost and session data for two different coding agents live in two opaque directories with no shared view.
- **Solution:** one TUI that reads both, prices every model accurately, and lets you clean up safely — to the trash, with recovery snapshots.

---

## Demo

<!--
TODO: the GIF below predates the Codex + combined-dashboard update — re-record with:
- `terminal-gif-maker` skill (say "터미널 데모 GIF 만들어줘")
- output: docs/demo.gif (+ keep the .tape so it can be regenerated)
-->

<img src="docs/demo.gif" alt="asm demo" width="780"/>

---

## ✨ Features

### Combined dashboard
- **Cost across both agents** with an in-app source filter — press `s` for All / Claude / Codex
- Per-model token & cost breakdown (Opus / Sonnet / Haiku / GPT-5.x), each row tagged by source
- Daily / weekly / monthly usage tables and a Top-10 project cost chart
- Accurate, current pricing from a LiteLLM-sourced rate table (new Opus/GPT models priced correctly, not at stale rates)

### Claude management
- **Projects:** tree from `.claude.json`, expand to preview session conversations, trash sessions, remove projects from config
- **Orphan cleanup:** detect and bulk-clean sessions, file-history, debug, and task entries with no matching project
- **Duplicate sessions:** find the same session copied across projects and delete individual copies
- **Migration:** copy sessions between projects (originals preserved), with paths auto-rewritten

### Codex sessions
- Browse `~/.codex` rollout sessions grouped by working directory
- Preview conversations and trash individual sessions

### Safe by default
- Every delete goes to the **OS trash** and is recorded in an audit log
- **Recovery snapshots** are taken before trashing (Claude and Codex)
- Backups for Claude (config / settings / plugins / sessions / full) and Codex (sessions, excluding huge caches), with auto safety-backup and rollback on restore

---

## How it works

```
   ~/.claude  ┐
              ├──►  asm  ──►  one dashboard  ──►  filter: All / Claude / Codex
   ~/.codex   ┘              (cost · sessions · cleanup · backup)
```

`asm` reads both data directories directly — no daemon, no config. Claude data is grouped by project; Codex sessions are grouped by working directory. Pricing is computed from each session's recorded token usage.

| Path | What's there |
|:---|:---|
| `~/.claude.json` · `~/.claude/projects/` | Claude projects, costs, session JSONL |
| `~/.claude/file-history/` · `debug/` · `tasks/` | Snapshots, debug logs, per-session task lists |
| `~/.codex/sessions/` | Codex rollout session files |
| `~/.asm/backups/` · `trash-log.jsonl` | Backups (auto-migrated from old `~/.cc-tui`) and the deletion audit log |

---

## 🛠️ Tech Stack

- **TUI:** [Textual](https://github.com/Textualize/textual) + [Rich](https://github.com/Textualize/rich)
- **Safety:** [send2trash](https://github.com/arsenetar/send2trash) (OS trash, not `rm`)
- **Sessions:** [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) with a JSONL fallback parser
- **Python:** 3.11+

---

## 🚀 Getting started

### Install (recommended)

```bash
# uv
uv tool install agent-session-manager

# pip
pip install agent-session-manager
```

Both install a single `asm` command. On first run, data from the previous `~/.cc-tui` location is migrated to `~/.asm` automatically.

<details>
<summary><strong>Run from source</strong></summary>

```bash
git clone https://github.com/Bae-ChangHyun/agent-session-manager.git
cd agent-session-manager
uv sync && uv run asm
```

</details>

### Usage

```bash
asm                       # Launch — shows Claude + Codex together
asm --source codex        # Start with the dashboard filtered to Codex
asm --path /your/project  # Limit to one Claude project
asm --lang ko             # Korean UI  (or set ASM_LANG=ko)
asm --no-update-check     # Skip the startup update check
```

Both sources are always available; `--source` only sets the dashboard's initial filter, which you change anytime with `s`.

### Keyboard

| Key | Action |
|:---:|:---|
| `F1`–`F6` | Switch tabs |
| `s` | Dashboard source filter (All / Claude / Codex) |
| `Tab` / `Shift+Tab` · `1` `2` `3` | Dashboard period (Daily / Weekly / Monthly) |
| `d` / `D` | Trash selected / all orphaned |
| `Space` · `Enter` | Toggle selection · Preview conversation |
| `r` · `q` | Refresh all · Quit |

### Staying up to date

When a newer release is on PyPI, `asm` offers a `y/N` upgrade prompt on startup (via `uv tool` or `pip`). It's skipped in non-interactive shells and when offline.

---

## 🗺️ Roadmap

- [ ] Re-record the demo GIF for the combined Claude + Codex dashboard
- [ ] Codex session **restore** (backup / list / delete exist today; restore does not)
- [ ] Per-source disk-usage and retention hints in the data overview
- [ ] Publish to PyPI as `agent-session-manager`

---

## ⚠️ Status & scope

- **Personal / pre-release**, under active development.
- Operates directly on Claude Code and Codex internal data — **back up before bulk deletes**.
- Deletes go to the OS trash with recovery snapshots; nothing is `rm`'d in place.
- No warranty. Not affiliated with Anthropic or OpenAI.

---

## 📄 License

[MIT](LICENSE)

<div align="center">
<br/>
Made with <b>Claude Code</b> · and now <b>Codex</b> too
</div>
