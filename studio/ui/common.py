"""Helpers shared by UI modules: cached probes, safe saves, formatting."""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from studio import config
from studio.ffmpeg_tools import FFmpegError, probe


@st.cache_data(show_spinner=False, max_entries=256)
def cached_duration(path_str: str, mtime: float) -> float:  # noqa: ARG001 - mtime busts cache
    try:
        return probe(Path(path_str)).duration
    except FFmpegError:
        return 0.0


def duration_of(path: Path) -> float:
    try:
        return cached_duration(str(path), path.stat().st_mtime)
    except OSError:
        return 0.0


def save_bytes_once(data: bytes, suffix: str, prefix: str = "upload") -> Path:
    """Content-addressed save into the upload folder (identical bytes -> same file)."""
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(data).hexdigest()[:16]
    target = config.UPLOAD_DIR / f"{prefix}_{digest}{suffix.lower()}"
    if not target.exists():
        target.write_bytes(data)
    return target


def fmt_bytes(num: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if num < 1024 or unit == "ТБ":
            return f"{num:.0f} {unit}" if unit == "Б" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} ТБ"
