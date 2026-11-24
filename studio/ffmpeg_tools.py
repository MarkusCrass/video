"""ffmpeg discovery, probing and safe subprocess execution.

Binary lookup order: system `ffmpeg` (shutil.which) -> `imageio_ffmpeg`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class FFmpegError(RuntimeError):
    """ffmpeg/ffprobe failed; message carries the last lines of stderr."""


@dataclass(frozen=True)
class ProbeInfo:
    duration: float
    has_audio: bool
    has_video: bool


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - dependency is required
        raise FFmpegError("Не найден ffmpeg: установите ffmpeg или imageio-ffmpeg") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _tail(text: str, lines: int = 6) -> str:
    rows = [row for row in (text or "").splitlines() if row.strip()]
    return " | ".join(rows[-lines:]) or "неизвестная ошибка"


def run_ffmpeg(args: list[str], timeout: int = 1800) -> None:
    """Run ffmpeg with `args` (no shell). Raises FFmpegError on failure."""
    cmd = [ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("ffmpeg: превышено время обработки") from exc
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg (код {proc.returncode}): {_tail(proc.stderr)}")


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+[^\n]*:\s*Audio:")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+[^\n]*:\s*Video:")


def probe(path: Path) -> ProbeInfo:
    """Read duration and stream presence using `ffmpeg -i` (no ffprobe needed)."""
    if not Path(path).exists():
        raise FFmpegError(f"Файл не найден: {path}")
    proc = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path)],
        capture_output=True, text=True, errors="replace", timeout=120,
    )
    text = proc.stderr or ""
    match = _DURATION_RE.search(text)
    duration = 0.0
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0 and not _VIDEO_RE.search(text) and not _AUDIO_RE.search(text):
        raise FFmpegError(f"Не удалось прочитать файл: {Path(path).name}")
    return ProbeInfo(
        duration=duration,
        has_audio=bool(_AUDIO_RE.search(text)),
        has_video=bool(_VIDEO_RE.search(text)),
    )


def detect_cut_points(path: Path, max_seconds: float = 900, threshold: float = 0.3) -> list[float]:
    """Timestamps of scene changes (keyframe based, fast). Empty list on failure."""
    cmd = [
        ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "info",
        "-skip_frame", "nokey", "-t", str(max_seconds), "-i", str(path),
        "-an", "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=600
        )
    except subprocess.TimeoutExpired:
        return []
    times = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", proc.stderr or "")]
    return sorted(set(round(t, 2) for t in times))
