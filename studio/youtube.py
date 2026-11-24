"""YouTube search and download through yt-dlp (`python -m yt_dlp`).

Failures of individual videos are reported as `YouTubeError` so the caller can
skip them and continue with the next search result.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from studio import config

# Prefer MP4/M4A (plays everywhere, no re-mux), cap at 1080p to save time/disk.
DOWNLOAD_FORMAT = (
    "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
    "b[height<=1080][ext=mp4]/"
    "bv*[height<=1080]+ba/"
    "b[height<=1080]/best"
)
_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov")


class YouTubeError(RuntimeError):
    """A search or download step failed (message is user-facing)."""


@dataclass(frozen=True)
class Candidate:
    video_id: str
    title: str
    url: str
    duration: float | None
    channel: str = ""


def _yt_dlp(*args: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-config", *args]


def _last_error(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR")] or lines
    if not errors:
        return "неизвестная ошибка yt-dlp"
    message = errors[-1].split("; please report")[0]
    return message[:300]


def parse_search_output(stdout: str) -> list[Candidate]:
    """Turn `--dump-json` lines into candidates (invalid lines are ignored)."""
    result: list[Candidate] = []
    seen: set[str] = set()
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        video_id = str(entry.get("id") or "")
        if not video_id or video_id in seen or entry.get("is_live"):
            continue
        seen.add(video_id)
        url = entry.get("webpage_url") or entry.get("url") or ""
        if not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"
        duration = entry.get("duration")
        result.append(Candidate(
            video_id=video_id,
            title=str(entry.get("title") or "Без названия"),
            url=str(url),
            duration=float(duration) if isinstance(duration, (int, float)) else None,
            channel=str(entry.get("channel") or entry.get("uploader") or ""),
        ))
    return result


def is_usable(candidate: Candidate, min_seconds: float) -> bool:
    """Skip videos that are too long, too short or known to be unavailable."""
    if candidate.duration is None:
        return True  # checked after download with ffmpeg
    return min_seconds <= candidate.duration <= config.MAX_SOURCE_SECONDS


def search(query: str, limit: int) -> list[Candidate]:
    """Search YouTube for `query` and return up to `limit` candidates."""
    query = query.strip()
    if not query:
        raise YouTubeError("Введите поисковый запрос")
    cmd = _yt_dlp("--flat-playlist", "--dump-json", "--skip-download",
                  f"ytsearch{max(1, int(limit))}:{query}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=240)
    except subprocess.TimeoutExpired as exc:
        raise YouTubeError("YouTube не ответил вовремя (поиск)") from exc
    candidates = parse_search_output(proc.stdout)
    if not candidates and proc.returncode != 0:
        raise YouTubeError(f"Поиск YouTube не удался: {_last_error(proc.stderr)}")
    return candidates


def download(url: str, target_base: Path, ffmpeg_location: str) -> Path:
    """Download `url` to `<target_base>.<ext>` and return the final file path."""
    target_base = Path(target_base)
    target_base.parent.mkdir(parents=True, exist_ok=True)
    cmd = _yt_dlp(
        "--no-playlist", "--no-progress", "--match-filter", "!is_live",
        "--ffmpeg-location", ffmpeg_location,
        "--remote-components", "ejs:github",
        "--socket-timeout", "30", "--retries", "3", "--fragment-retries", "3",
        "-f", DOWNLOAD_FORMAT, "--merge-output-format", "mp4",
        "-o", f"{target_base}.%(ext)s", url,
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=1500)
    except subprocess.TimeoutExpired as exc:
        raise YouTubeError("Скачивание заняло слишком много времени") from exc
    if proc.returncode != 0:
        raise YouTubeError(_last_error(proc.stderr or proc.stdout))
    files = [
        p for p in target_base.parent.glob(f"{target_base.name}.*")
        if p.suffix.lower() in _VIDEO_EXTS and p.is_file()
    ]
    if not files:
        raise YouTubeError("yt-dlp не создал видеофайл")
    return max(files, key=lambda p: p.stat().st_size)
