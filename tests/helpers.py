"""Shared test setup: isolated data dir + synthetic media generated with ffmpeg."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = Path(tempfile.mkdtemp(prefix="studio_tests_"))
os.environ["STUDIO_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("APP_PASSWORD", "moon2026")

from studio.ffmpeg_tools import ffmpeg_path, run_ffmpeg  # noqa: E402

FIXTURES = DATA_DIR / "fixtures"


def make_fixtures() -> dict[str, Path]:
    """Create small synthetic media once per test run."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    files = {
        # 16:9 source with audio and moving pattern: 40 s
        "src169": (FIXTURES / "src169.mp4", [
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=40",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]),
        # 9:16 phone clip without audio: 20 s
        "src916": (FIXTURES / "src916_noaudio.mp4", [
            "-f", "lavfi", "-i", "testsrc=size=720x1280:rate=25:duration=20",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]),
        "music": (FIXTURES / "music.mp3", [
            "-f", "lavfi", "-i", "sine=frequency=220:duration=60", "-c:a", "libmp3lame"]),
        "voice": (FIXTURES / "voice.wav", [
            "-f", "lavfi", "-i", "sine=frequency=660:duration=6", "-ac", "1", "-ar", "16000"]),
        "voice_m4a": (FIXTURES / "voice.m4a", [
            "-f", "lavfi", "-i", "sine=frequency=330:duration=5", "-c:a", "aac"]),
    }
    for name, (path, args) in files.items():
        if not path.exists():
            run_ffmpeg([*args, str(path)])
    return {name: path for name, (path, _) in files.items()}


def video_size(path: Path) -> tuple[int, int] | None:
    """Parse WxH of the first video stream from `ffmpeg -i` output."""
    import re
    import subprocess

    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path)],
                          capture_output=True, text=True, errors="replace")
    match = re.search(r"Video:.*?,\s(\d{3,5})x(\d{3,5})", proc.stderr or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def cleanup() -> None:
    shutil.rmtree(DATA_DIR, ignore_errors=True)
