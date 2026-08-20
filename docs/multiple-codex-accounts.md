# Multiple Codex accounts

Codex keeps **one home directory per login**. If you sign in with a second
account, its sessions do not appear in `~/.codex` — they live in a separate
home, commonly `~/.codex-<label>`:

```
~/.codex          25,739 rollouts   account A
~/.codex-hermes       23 rollouts   account B
```

This is an unusual setup, so asm assumes a single home until told otherwise.
Everything below is opt-in configuration for people who do run more than one.

## How asm picks homes

Resolution order, first match wins:

| Order | Source | Use it for |
| --- | --- | --- |
| 1 | `--codex-home PATH` (repeatable) | one-off runs, scripts, any layout |
| 2 | `ASM_CODEX_HOMES` (`os.pathsep`-separated) | permanent setup via your shell rc |
| 3 | `CODEX_HOME` (or `~/.codex`) **plus** sibling `~/.codex-*` dirs holding a `sessions/` tree | the common layout, no setup |

Rule 3 is a convenience for the usual naming pattern only. If your homes live
anywhere else — `~/work/.codex`, `/opt/codex-ci` — name them with rule 1 or 2.
Nothing is guessed beyond that pattern.

```bash
# one-off
asm --codex-home ~/work/.codex --codex-home /opt/codex-ci import list --to claude

# permanent (~/.zshrc)
export ASM_CODEX_HOMES="$HOME/.codex:$HOME/work/.codex"
```

## Check what is actually scanned

```console
$ asm import homes
Codex homes scanned (--codex-home / ASM_CODEX_HOMES override this):
   /home/you/.codex  25739 sessions
   /home/you/.codex-work  23 sessions
```

A path that does not exist is printed with `(missing)` rather than silently
contributing nothing, so a typo in `ASM_CODEX_HOMES` is visible immediately.

## What spans every home

- Session lists, search, and previews
- Dashboard totals and cost/token aggregation (the usage ledger ingests all homes)
- `asm import session <id>` — an id is looked up in every home, and the source
  home is reported: `codex -> claude: 139 turns  cwd=/home/you/notes  [.codex-hermes]`
- `asm import list` — merged, newest activity first
- Trashing a session and restoring it from a recovery snapshot

## What is still single-home

These read the **primary** home only (`CODEX_HOME`, or `~/.codex`):

- `asm backup create --type codex` — back up a second home by pointing
  `CODEX_HOME` at it for that run
- MCP server import (`asm import mcp`) — reads that home's `config.toml`
- The import ledger (`external_agent_session_imports.json`) that dedupes
  Claude → Codex imports

If you need any of these per-account today, run the command with
`CODEX_HOME=~/.codex-<label>` set.
