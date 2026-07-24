"""Service for migrating Claude Code sessions between projects."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from send2trash import send2trash

from asm.models import PROJECTS_DIR, decode_path_hint, encode_path

logger = logging.getLogger(__name__)


@dataclass
class MigrateResult:
    """Result of a migration operation."""

    success: bool
    sessions_copied: int = 0
    sessions_skipped: int = 0
    memory_copied: bool = False
    message: str = ""


def get_available_projects() -> list[tuple[str, str]]:
    """Get list of (encoded_name, decoded_hint) for available project dirs."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.is_dir():
            hint = decode_path_hint(d.name)
            result.append((d.name, hint))
    return result


def find_similar_dirs(target_encoded: str) -> list[str]:
    """Find directories similar to the target encoded name."""
    if not PROJECTS_DIR.exists():
        return []
    # Extract key parts for matching
    parts = set(target_encoded.strip("-").split("-"))
    results = []
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir():
            dir_parts = set(d.name.strip("-").split("-"))
            overlap = parts & dir_parts
            if len(overlap) >= len(parts) * 0.5:
                results.append(d.name)
    return results


def migrate_sessions(
    source_path: str,
    target_path: str,
    mode: str = "append",
    source_encoded: str | None = None,
    target_encoded: str | None = None,
    session_ids: list[str] | None = None,
) -> MigrateResult:
    """Migrate sessions from source project to target project.

    Args:
        source_path: Absolute path of source project (for display/path updates)
        target_path: Absolute path of target project (for display/path updates)
        mode: "append" (keep existing, skip duplicates) or "overwrite"
        source_encoded: Pre-encoded source dir name (avoids lossy re-encoding)
        target_encoded: Pre-encoded target dir name (avoids lossy re-encoding)
        session_ids: If provided, only migrate these specific session IDs.
                     If None, migrate all sessions.
    """
    source_encoded = source_encoded or encode_path(source_path)
    target_encoded = target_encoded or encode_path(target_path)
    source_dir = PROJECTS_DIR / source_encoded
    target_dir = PROJECTS_DIR / target_encoded

    # Validate source
    if not source_dir.exists():
        similar = find_similar_dirs(source_encoded)
        msg = f"Source not found: {source_dir}"
        if similar:
            msg += f"\nSimilar: {', '.join(similar)}"
        return MigrateResult(success=False, message=msg)

    # Check for session files (filter by session_ids if provided)
    all_sessions = list(source_dir.glob("*.jsonl"))
    if session_ids is not None:
        id_set = set(session_ids)
        source_sessions = [f for f in all_sessions if f.stem in id_set]
    else:
        source_sessions = all_sessions
    if not source_sessions:
        return MigrateResult(success=False, message="No session files to migrate")

    # Prepare target
    target_dir.mkdir(parents=True, exist_ok=True)

    # Overwrite mode: clear existing
    if mode == "overwrite":
        for existing in target_dir.iterdir():
            send2trash(str(existing))

    # Copy sessions (tracking exactly which files landed in this run — only
    # those may be path-rewritten below, or repeat runs corrupt earlier copies)
    copied = 0
    skipped = 0
    copied_files: list[Path] = []
    for src_file in source_sessions:
        dest_file = target_dir / src_file.name
        if mode == "append" and dest_file.exists():
            skipped += 1
            continue
        shutil.copy2(str(src_file), str(dest_file))
        copied += 1
        copied_files.append(dest_file)

    # Copy memory
    memory_copied = False
    source_memory = source_dir / "memory"
    if source_memory.exists():
        target_memory = target_dir / "memory"
        if mode == "overwrite" and target_memory.exists():
            shutil.rmtree(str(target_memory))
        if not target_memory.exists():
            shutil.copytree(str(source_memory), str(target_memory))
            memory_copied = True
        else:
            # Append: copy only new files
            for f in source_memory.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(source_memory)
                    dest = target_memory / rel
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(f), str(dest))
                        memory_copied = True

    # Copy sessions-index.json
    src_index = source_dir / "sessions-index.json"
    index_copied: Path | None = None
    if src_index.exists():
        dest_index = target_dir / "sessions-index.json"
        if mode == "overwrite" or not dest_index.exists():
            shutil.copy2(str(src_index), str(dest_index))
            index_copied = dest_index

    # Update paths in the files copied THIS run only — files from earlier runs
    # already point at the target, and rewriting them again nests the path
    # (source is often a prefix of target).
    if source_path != target_path:
        _update_paths(copied_files, index_copied, source_path, target_path,
                      source_encoded, target_encoded)

    msg = f"{copied} sessions migrated"
    if skipped:
        msg += f", {skipped} already in target (skipped)"
    return MigrateResult(
        success=True,
        sessions_copied=copied,
        sessions_skipped=skipped,
        memory_copied=memory_copied,
        message=f"{msg} ({source_path} -> {target_path})",
    )


_PATH_FIELDS = {"cwd", "projectPath", "path", "directory", "projectDir", "workingDirectory"}


def _replace_in_obj(obj: object, old: str, new: str, restrict_keys: bool = True) -> None:
    """Recursively replace string values in a JSON-like object.

    When restrict_keys is True, only replaces values in known path-containing
    fields to avoid corrupting message content.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and old in v:
                if not restrict_keys or k in _PATH_FIELDS:
                    obj[k] = v.replace(old, new)
            elif isinstance(v, (dict, list)):
                _replace_in_obj(v, old, new, restrict_keys)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                _replace_in_obj(item, old, new, restrict_keys)


def _update_paths(
    copied_files: list[Path],
    copied_index: Path | None,
    source_path: str,
    target_path: str,
    source_encoded: str,
    target_encoded: str,
) -> None:
    """Update path references in the files copied by this run."""
    # Update JSONL files - parse each line as JSON to avoid partial matches
    for jsonl in copied_files:
        try:
            lines = jsonl.read_text().splitlines()
            updated = []
            modified = False
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    before = json.dumps(obj, ensure_ascii=False)
                    _replace_in_obj(obj, source_path, target_path, restrict_keys=True)
                    after = json.dumps(obj, ensure_ascii=False)
                    updated.append(after)
                    if before != after:
                        modified = True
                except json.JSONDecodeError:
                    updated.append(line)
            if modified:
                jsonl.write_text("\n".join(updated) + "\n")
        except OSError as e:
            logger.warning("Path rewrite failed for %s: %s", jsonl.name, e)

    # sessions-index.json - parse as JSON, not string replace
    idx = copied_index
    if idx is not None and idx.exists():
        try:
            data = json.loads(idx.read_text())
            _replace_in_obj(data, source_path, target_path, restrict_keys=False)
            _replace_in_obj(data, source_encoded, target_encoded, restrict_keys=False)
            idx.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("sessions-index.json rewrite failed for %s: %s", idx, e)
