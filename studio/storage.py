"""Disk usage, temp-file housekeeping and output listing."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from studio import config


@dataclass(frozen=True)
class DiskInfo:
    total: int
    used: int
    free: int

    @property
    def used_fraction(self) -> float:
        return self.used / self.total if self.total else 0.0


def disk_info(path: Path | None = None) -> DiskInfo:
    usage = shutil.disk_usage(path or config.DATA_DIR)
    return DiskInfo(total=usage.total, used=usage.used, free=usage.free)


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def dir_size(folder: Path) -> int:
    if not folder.exists():
        return 0
    total = 0
    for item in folder.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def temp_size() -> int:
    return dir_size(config.TMP_DIR)


def cleanup_old_temp(max_age_hours: float = config.TEMP_MAX_AGE_HOURS) -> int:
    """Delete temp files older than `max_age_hours`. Returns removed file count."""
    if not config.TMP_DIR.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for item in config.TMP_DIR.rglob("*"):
        if item.is_file() and item.stat().st_mtime < cutoff:
            try:
                item.unlink()
                removed += 1
            except OSError:
                pass
    # Remove empty sub-folders (bottom-up), never the TMP_DIR root itself.
    for folder in sorted(config.TMP_DIR.rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            try:
                folder.rmdir()
            except OSError:
                pass
    return removed


def clear_temp() -> int:
    """Remove everything inside TMP_DIR (the folder itself is kept)."""
    if not config.TMP_DIR.exists():
        return 0
    removed = 0
    for item in config.TMP_DIR.iterdir():
        if not _is_inside(item, config.TMP_DIR):
            continue
        if item.is_dir():
            removed += sum(1 for f in item.rglob("*") if f.is_file())
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
                removed += 1
            except OSError:
                pass
    config.ensure_dirs()
    return removed


def remove_path(path: Path) -> None:
    """Delete a file or directory, but only if it lives inside TMP_DIR or OUTPUT_DIR/MUSIC_DIR."""
    allowed = (config.TMP_DIR, config.OUTPUT_DIR, config.MUSIC_DIR)
    if not any(_is_inside(path, root) for root in allowed):
        raise PermissionError(f"Refusing to delete outside studio folders: {path}")
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def list_outputs() -> list[Path]:
    """Finished MP4 files, newest first."""
    if not config.OUTPUT_DIR.exists():
        return []
    files = [p for p in config.OUTPUT_DIR.glob("*.mp4") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
