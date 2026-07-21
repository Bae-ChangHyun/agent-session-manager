<div align="center">

# agent-session-manager

**One terminal dashboard for everything Claude Code and Codex leave behind.**
See cost, browse sessions, and clean up `~/.claude` and `~/.codex` — side by side, with a Claude / Codex filter.

[![PyPI](https://img.shields.io/pypi/v/agent-session-manager?style=flat-square&color=blue)](https://pypi.org/project/agent-session-manager/)
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

The combined dashboard (cost across both agents, source-tagged rows), then the
same view filtered to **Claude** and to **Codex**:

<img src="docs/demo.gif" alt="asm demo" width="820"/>

---

## ✨ Features

### Combined dashboard
- **Cost across both agents** with a source filter — **click** `All / Claude / Codex` or press `s`
- Per-model token & cost breakdown (Opus / Sonnet / Haiku / GPT-5.x), each row tagged by source
- Daily / weekly / monthly usage tables (one scan, all periods) and a Top-10 project cost chart
- Accurate, current pricing from a LiteLLM-sourced rate table (Claude 5 family, new Opus, and GPT-5.x priced correctly, not at stale rates)

### Unified sessions (Claude + Codex)
- One tree: Claude projects and Codex working directories together, each session tagged **C** / **X**
- Expand a project to preview conversations from either agent; trash individual sessions
- **Edit instructions:** per project, view/edit/create `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `AGENTS.local.md` in a built-in editor (Ctrl+S to save)
- **Move a Codex session** to another working directory (rewrites its `cwd`, which is how `codex resume --cd` associates sessions)
- **Orphan cleanup:** detect and bulk-clean Claude sessions, file-history, debug, and task entries with no matching project
- **Duplicate sessions:** find the same session copied across projects and delete individual copies
- **Empty sessions:** clean stub sessions that hold only a title/metadata and no conversation (can't be resumed)
- **Migration:** copy Claude sessions between projects (originals preserved), with paths auto-rewritten

### Safe by default
- Every delete goes to the **OS trash** and is recorded in an audit log
- **Recovery snapshots** are taken before trashing (Claude and Codex), with a size/age cap so they don't pile up
- Backups **and restore** for Claude (config / settings / plugins / sessions / full) and Codex (sessions, excluding huge caches); restore is rollback-safe (the live dir is moved aside and put back if the copy fails), and credential-bearing backups are written owner-only (0600)

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

### Headless CLI

Every feature is also available as a subcommand — handy for scripts and AI agents. In a terminal you get rich tables; piped output is plain text, and `--json` gives machine-readable output.

```bash
# Read-only
asm cost --period weekly          # Cost/token stats per model & period
asm projects                      # All projects (Claude + Codex)
asm sessions --search "firewall"  # Search sessions by title
asm preview <session-id>          # Print a conversation
asm resume <session-id>           # cd into its project & resume (Claude/Codex)
asm backup list / asm recovery list

# Destructive — always confirms first (skip with --yes); everything goes
# through the OS trash + recovery snapshots, same as the TUI.
asm clean empty --dry-run         # empty | orphaned | debug | todos
asm trash <session-id>
asm backup create --type full     # config|full|settings|plugins|sessions|codex
asm backup restore <path> / asm recovery restore <id>
asm migrate /old/project /new/project
```

### Keyboard

| Key | Action |
|:---:|:---|
| `F1`–`F6` | Switch tabs |
| `s` / click | Dashboard source filter (All / Claude / Codex) |
| `Tab` / `Shift+Tab` · `1` `2` `3` | Dashboard period (Daily / Weekly / Monthly) |
| `d` / `D` | Trash selected / all orphaned |
| `Space` · `Enter` | Toggle selection · Preview conversation |
| `r` · `q` | Refresh all · Quit |

### Staying up to date

When a newer release is on PyPI, `asm` offers a `y/N` upgrade prompt on startup (via `uv tool` or `pip`). It's skipped in non-interactive shells and when offline.

---

## 🗺️ Roadmap

- [ ] Per-source disk-usage in the data overview
- [ ] Incremental (mtime-based) usage scan for very large `~/.claude` trees
- [ ] ruff + mypy in CI

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
