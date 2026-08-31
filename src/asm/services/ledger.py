"""Persistent usage ledger (SQLite at ~/.asm/usage.db).

Solves three problems the in-memory scan cannot:

- **Incremental**: files are re-parsed only when (mtime, size) changed since
  the last scan, so a refresh stats the tree instead of re-reading it.
- **Prices frozen at scan time**: cost is computed with the rates in effect
  when a session is first parsed and stored; later rate changes never
  re-value old sessions. (The initial backfill necessarily uses current
  rates — historical rate data does not exist anywhere.)
- **Survives deletion**: rows are kept when the source file disappears
  (Claude Code prunes transcripts via cleanupPeriodDays), so cost history
  outlives the session files. Delete ~/.asm/usage.db to rebuild from disk.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

ProgressCB = Callable[[str, int, int], None]  # (source, done, total_new)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanned_files(
    path TEXT PRIMARY KEY, mtime REAL, size INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS claude_messages(
    msg_id TEXT PRIMARY KEY, ts TEXT, model TEXT,
    input INTEGER, output INTEGER, cache_read INTEGER, cache_create INTEGER,
    cost REAL, project_dir TEXT, file TEXT);
CREATE INDEX IF NOT EXISTS idx_claude_file ON claude_messages(file);
CREATE TABLE IF NOT EXISTS codex_sessions(
    path TEXT PRIMARY KEY, session_id TEXT, cwd TEXT, model TEXT,
    started TEXT, mtime REAL, size INTEGER,
    input INTEGER, cached_input INTEGER, output INTEGER, cost REAL,
    first_prompt TEXT, git_branch TEXT);
"""

_PROGRESS_EVERY = 200


class LedgerParseError(ValueError):
    pass


def _json_object(line: str, path: Path, line_number: int) -> dict:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise LedgerParseError(
            f"{path}: line {line_number}: invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise LedgerParseError(
            f"{path}: line {line_number}: JSON value must be an object"
        )
    return value


def _validate_jsonl_objects(path: Path) -> None:
    with open(path) as file:
        for line_number, line in enumerate(file, 1):
            _json_object(line, path, line_number)


def _db_path() -> Path:
    from asm import models

    return models.APP_DATA_DIR / "usage.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)  # transcripts/prompts land in this DB
    except OSError:
        pass
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    try:
        path.chmod(0o600)  # rows carry prompt snippets
    except OSError:
        pass
    return conn


def _known_files(conn: sqlite3.Connection, source: str) -> dict[str, tuple[float, int]]:
    return {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT path, mtime, size FROM scanned_files WHERE source = ?", (source,)
        )
    }


def _changed(known: dict, path: Path) -> tuple[float, int] | None:
    """(mtime, size) when the file is new/changed, None when up to date."""
    try:
        st = path.stat()
    except OSError:
        return None
    prev = known.get(str(path))
    stamp = (st.st_mtime, st.st_size)
    return None if prev == stamp else stamp


def _load_rates_if_needed(new_count: int) -> None:
    if new_count:
        from asm.services import pricing

        pricing.load_live_rates()


# ── Claude ───────────────────────────────────────────────────────────────


def update_claude(progress: ProgressCB | None = None) -> int:
    """Parse new/changed Claude session files into the ledger. Returns count."""
    from asm.services import claude_data

    root = claude_data.PROJECTS_DIR
    if not root.exists():
        return 0
    conn = _connect()
    try:
        known = _known_files(conn, "claude")
        todo: list[tuple[Path, str, tuple[float, int]]] = []
        for d in root.iterdir():
            if not d.is_dir():
                continue
            for jsonl in d.rglob("*.jsonl"):
                stamp = _changed(known, jsonl)
                if stamp is not None:
                    todo.append((jsonl, d.name, stamp))
        _load_rates_if_needed(len(todo))
        updated = 0
        for i, (jsonl, project_dir, stamp) in enumerate(todo, 1):
            try:
                _ingest_claude_file(conn, jsonl, project_dir, stamp)
            except (LedgerParseError, OSError) as exc:
                logger.error("Cannot ingest Claude usage from %s: %s", jsonl, exc)
            else:
                updated += 1
            if progress and (i % _PROGRESS_EVERY == 0 or i == len(todo)):
                progress("claude", i, len(todo))
        conn.commit()
        return updated
    finally:
        conn.close()


def _ingest_claude_file(
    conn: sqlite3.Connection, jsonl: Path, project_dir: str, stamp: tuple[float, int]
) -> None:
    from asm.services.pricing import calc_cost, is_billable

    rows = []
    with open(jsonl) as f:
        for line_number, line in enumerate(f, 1):
            try:
                msg = _json_object(line, jsonl, line_number)
                if msg.get("type") != "assistant":
                    continue
                m = msg.get("message", {})
                usage = m.get("usage")
                model = m.get("model", "")
                ts_str = msg.get("timestamp", "")
                msg_id = m.get("id", "")
                if not usage or not ts_str or not msg_id:
                    continue
                if not is_billable(model):
                    continue
                rows.append((
                    msg_id, ts_str, model,
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    usage.get("cache_read_input_tokens", 0),
                    usage.get("cache_creation_input_tokens", 0),
                    calc_cost(usage, model),
                    project_dir, str(jsonl),
                ))
            except LedgerParseError:
                raise
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise LedgerParseError(
                    f"{jsonl}: line {line_number}: invalid Claude usage record: {exc}"
                ) from exc
    # A rewrite (e.g. migrate) can drop lines — replace this file's rows wholesale.
    conn.execute("DELETE FROM claude_messages WHERE file = ?", (str(jsonl),))
    conn.executemany(
        "INSERT OR REPLACE INTO claude_messages VALUES (?,?,?,?,?,?,?,?,?,?)", rows
    )
    conn.execute(
        "INSERT OR REPLACE INTO scanned_files VALUES (?,?,?,?)",
        (str(jsonl), stamp[0], stamp[1], "claude"),
    )


def claude_records() -> dict[str, dict]:
    """{msg_id: {usage, model, ts_str, project_dir, cost}} over the whole ledger."""
    conn = _connect()
    try:
        out: dict[str, dict] = {}
        for row in conn.execute(
            "SELECT msg_id, ts, model, input, output, cache_read, cache_create,"
            " cost, project_dir FROM claude_messages"
        ):
            out[row[0]] = {
                "usage": {
                    "input_tokens": row[3],
                    "output_tokens": row[4],
                    "cache_read_input_tokens": row[5],
                    "cache_creation_input_tokens": row[6],
                },
                "model": row[2],
                "ts_str": row[1],
                "project_dir": row[8],
                "cost": row[7],
            }
        return out
    finally:
        conn.close()


# ── Codex ────────────────────────────────────────────────────────────────


def update_codex(progress: ProgressCB | None = None) -> int:
    """Parse new/changed Codex rollouts into the ledger. Returns count."""
    from asm.services import codex_data

    if not codex_data.CODEX_SESSIONS_DIR.exists():
        return 0
    conn = _connect()
    try:
        known = _known_files(conn, "codex")
        todo: list[tuple[Path, tuple[float, int]]] = []
        for f in codex_data._rollout_files():
            stamp = _changed(known, f)
            if stamp is not None:
                todo.append((f, stamp))
        _load_rates_if_needed(len(todo))
        updated = 0
        for i, (f, stamp) in enumerate(todo, 1):
            try:
                _ingest_codex_file(conn, f, stamp)
            except (LedgerParseError, OSError) as exc:
                logger.error("Cannot ingest Codex usage from %s: %s", f, exc)
            else:
                updated += 1
            if progress and (i % _PROGRESS_EVERY == 0 or i == len(todo)):
                progress("codex", i, len(todo))
            if i % 1000 == 0:
                conn.commit()  # keep the one-time backfill restartable
        conn.commit()
        return updated
    finally:
        conn.close()


def _ingest_codex_file(conn: sqlite3.Connection, f: Path, stamp: tuple[float, int]) -> None:
    from asm.services import codex_data, pricing

    _validate_jsonl_objects(f)
    try:
        info = codex_data._scan_session(f)
        if info is None:
            raise LedgerParseError(f"{f}: missing or unreadable session_meta")
        usage = info["usage"]
        model = info["model"] or codex_data.UNKNOWN_MODEL
        cost = pricing.calc_openai_cost(usage, model) if usage else 0.0
        conn.execute(
            "INSERT OR REPLACE INTO codex_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(f), info["id"], info["cwd"], info["model"],
                info["started"], info["mtime"], info["size"],
                usage.get("input_tokens", 0), usage.get("cached_input_tokens", 0),
                usage.get("output_tokens", 0), cost,
                info["first_prompt"], info["git_branch"],
            ),
        )
    except LedgerParseError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise LedgerParseError(f"{f}: invalid Codex usage record: {exc}") from exc
    conn.execute(
        "INSERT OR REPLACE INTO scanned_files VALUES (?,?,?,?)",
        (str(f), stamp[0], stamp[1], "codex"),
    )


def codex_records() -> list[dict]:
    """All Codex sessions in the ledger (deleted rollouts included), as the
    same info dicts the scanner produces, plus the frozen ``cost``."""
    conn = _connect()
    try:
        out = []
        for row in conn.execute(
            "SELECT path, session_id, cwd, model, started, mtime, size,"
            " input, cached_input, output, cost, first_prompt, git_branch"
            " FROM codex_sessions"
        ):
            usage = (
                {"input_tokens": row[7], "cached_input_tokens": row[8], "output_tokens": row[9]}
                if (row[7] or row[8] or row[9])
                else {}
            )
            out.append({
                "id": row[1], "cwd": row[2], "model": row[3],
                "first_prompt": row[11], "git_branch": row[12],
                "started": row[4], "usage": usage,
                "path": row[0], "size": row[6], "mtime": row[5],
                "cost": row[10],
            })
        return out
    finally:
        conn.close()
