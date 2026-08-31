"""App-managed recovery snapshots for trashed Claude Code data."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from send2trash import send2trash

from asm.models import CLAUDE_DIR, RECOVERY_BASE_DIR, RecoveryInfo

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")

# Retention for recovery snapshots — without this the "cleanup" tool would grow
# ~/.asm/recovery without bound (every trash duplicates data here + OS trash).
_MAX_ITEMS = 100
_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
_MAX_ITEM_BYTES = _MAX_TOTAL_BYTES


def _validate_original_path(path: Path) -> Path:
    from asm.services import codex_data

    resolved = path.resolve()
    codex_roots = [d.parent.resolve() for d in codex_data._session_dirs() if d.parent.exists()]
    roots = (CLAUDE_DIR.resolve(), *codex_roots)
    if not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError(f"Recovery path outside managed data dirs: {path}")
    return resolved


def _recovery_root(item_id: str) -> Path:
    root = (RECOVERY_BASE_DIR / item_id).resolve()
    if not root.is_relative_to(RECOVERY_BASE_DIR.resolve()):
        raise ValueError(f"Recovery item outside recovery dir: {item_id}")
    return root


def _payload_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def _safe_name(name: str) -> str:
    return (_SAFE_NAME_RE.sub("-", name).strip("-") or "item")[:48]


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if not _path_exists(path):
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _discard_snapshot(path: Path) -> None:
    try:
        _remove_path(path)
    except OSError as exc:
        logger.error("Failed to remove incomplete recovery snapshot %s: %s", path, exc)


def _copy_path(src: Path, dest: Path) -> None:
    if src.is_symlink():
        dest.symlink_to(src.readlink(), target_is_directory=src.is_dir())
    elif src.is_dir():
        shutil.copytree(
            src,
            dest,
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
    else:
        shutil.copy2(src, dest, follow_symlinks=False)


def _create_recovery_snapshot(path: Path, category: str) -> tuple[str, Path]:
    item_root: Path | None = None
    try:
        if not path.exists():
            raise FileNotFoundError(f"Recovery source does not exist: {path}")
        original = _validate_original_path(path)
        RECOVERY_BASE_DIR.mkdir(parents=True, exist_ok=True)
        RECOVERY_BASE_DIR.parent.chmod(0o700)
        RECOVERY_BASE_DIR.chmod(0o700)

        item_id = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{_safe_name(original.name)}"
        item_root = RECOVERY_BASE_DIR / item_id
        payload_root = item_root / "payload"
        item_root.mkdir(mode=0o700)
        item_root.chmod(0o700)
        payload_root.mkdir()

        snapshot = payload_root / original.name
        _copy_path(original, snapshot)

        size_bytes = _payload_size(snapshot)
        if size_bytes > _MAX_ITEM_BYTES:
            raise ValueError(
                f"Recovery snapshot is {size_bytes} bytes; limit is {_MAX_ITEM_BYTES}"
            )

        metadata = {
            "id": item_id,
            "name": original.name,
            "category": category,
            "original_path": str(original),
            "snapshot_path": str(snapshot),
            "created": datetime.now().timestamp(),
            "size_bytes": size_bytes,
        }
        (item_root / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2)
        )
        return item_id, item_root
    except (OSError, ValueError, shutil.Error):
        if item_root is not None:
            _discard_snapshot(item_root)
        raise


def create_recovery_snapshot(path: Path, category: str) -> str | None:
    """Create a recovery snapshot before the item is trashed."""
    item_root: Path | None = None
    try:
        item_id, item_root = _create_recovery_snapshot(path, category)
        _prune_snapshots({item_root})
        return item_id
    except (OSError, ValueError, shutil.Error) as exc:
        logger.warning("Failed to create recovery snapshot for %s: %s", path, exc)
        if item_root is not None:
            _discard_snapshot(item_root)
        return None


def create_recovery_snapshots(items: list[tuple[Path, str]]) -> list[str] | None:
    if not items:
        return []
    created: list[tuple[str, Path]] = []
    try:
        for path, category in items:
            created.append(_create_recovery_snapshot(path, category))
        _prune_snapshots({item_root for _, item_root in created})
        return [item_id for item_id, _ in created]
    except (OSError, ValueError, shutil.Error) as exc:
        logger.warning("Failed to create recovery snapshot batch: %s", exc)
        for _, item_root in created:
            _discard_snapshot(item_root)
        return None


def _prune_snapshots(protected: set[Path]) -> None:
    items = [d for d in RECOVERY_BASE_DIR.iterdir() if d.is_dir()]
    items.sort(key=lambda d: d.name)  # timestamp-prefixed → chronological
    sizes = {d: _payload_size(d) for d in items}
    protected_items = [item for item in items if item in protected]
    if len(protected_items) != len(protected):
        raise OSError("Recovery snapshot batch is incomplete")
    protected_size = sum(sizes[item] for item in protected_items)
    if len(protected_items) > _MAX_ITEMS or protected_size > _MAX_TOTAL_BYTES:
        raise OSError("Recovery snapshot batch exceeds retention limits")
    total = sum(sizes.values())
    # Oldest-first removal until within both caps.
    while items and (len(items) > _MAX_ITEMS or total > _MAX_TOTAL_BYTES):
        victim = next((item for item in items if item not in protected), None)
        if victim is None:
            raise OSError("Recovery snapshot batch cannot satisfy retention limits")
        items.remove(victim)
        total -= sizes.get(victim, 0)
        _remove_path(victim)


def list_recovery_items() -> list[RecoveryInfo]:
    """List app-managed recovery snapshots."""
    if not RECOVERY_BASE_DIR.exists():
        return []

    result: list[RecoveryInfo] = []
    try:
        for item_root in sorted(RECOVERY_BASE_DIR.iterdir(), reverse=True):
            if not item_root.is_dir():
                continue
            meta_path = item_root / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text())
                original_path = Path(data["original_path"])
                result.append(
                    RecoveryInfo(
                        id=data["id"],
                        name=data.get("name", item_root.name),
                        category=data.get("category", "generic"),
                        original_path=str(original_path),
                        snapshot_path=data["snapshot_path"],
                        created=float(data.get("created", 0)),
                        size_bytes=int(data.get("size_bytes", 0)),
                        original_exists=original_path.exists(),
                    )
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid recovery item %s: %s", item_root, exc)
    except OSError as exc:
        logger.warning("Failed to list recovery items: %s", exc)
    return result


def restore_recovery_item(item_id: str, overwrite: bool = False) -> tuple[bool, str]:
    """Restore a recovery snapshot to its original path."""
    try:
        item_root = _recovery_root(item_id)
        data = json.loads((item_root / "metadata.json").read_text())
        original = _validate_original_path(Path(data["original_path"]))
        # Trust boundary: the snapshot source must live under the recovery dir,
        # so a tampered metadata.json can't copy an arbitrary file into a managed
        # location (CWE-22/502).
        snapshot = Path(data["snapshot_path"])
        if not snapshot.resolve().is_relative_to(RECOVERY_BASE_DIR.resolve()):
            return False, "Snapshot path outside recovery dir"
        if not snapshot.exists():
            return False, "Snapshot payload is missing"

        original.parent.mkdir(parents=True, exist_ok=True)
        if _path_exists(original):
            if not overwrite:
                return False, "Original path already exists"

        transaction_id = uuid4().hex
        stage = original.with_name(f".{original.name}.asm-stage-{transaction_id}")
        rollback = original.with_name(f".{original.name}.asm-rollback-{transaction_id}")
        moved = False
        installed = False
        try:
            _copy_path(snapshot, stage)
            if snapshot.is_dir() != stage.is_dir() or _payload_size(snapshot) != _payload_size(stage):
                raise OSError("Recovery staging validation failed")
            if _path_exists(original):
                os.replace(original, rollback)
                moved = True
            os.replace(stage, original)
            installed = True
            if moved:
                send2trash(str(rollback))
                if _path_exists(rollback):
                    raise OSError("Previous live path was not moved to trash")
        except OSError:
            if installed and _path_exists(original):
                _remove_path(original)
            if moved and _path_exists(rollback):
                os.replace(rollback, original)
            _discard_snapshot(stage)
            raise
        return True, str(original)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, shutil.Error) as exc:
        logger.warning("Failed to restore recovery item %s: %s", item_id, exc)
        return False, str(exc)


def delete_recovery_item(item_id: str) -> bool:
    """Delete a recovery snapshot."""
    try:
        item_root = _recovery_root(item_id)
        if not item_root.exists():
            return False
        send2trash(str(item_root))
        return True
    except (OSError, ValueError) as exc:
        logger.warning("Failed to delete recovery item %s: %s", item_id, exc)
        return False
