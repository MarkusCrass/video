"""Central configuration: paths, limits, fonts and environment variables.

Values can be overridden in `.env` (see `.env.example`). Paths are created
lazily by `ensure_dirs()`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


# --- Security -------------------------------------------------------------
APP_PASSWORD: str = os.getenv("APP_PASSWORD", "").strip() or "moon2026"
PORT: int = int(os.getenv("PORT", "8501") or 8501)

# --- Data directories -----------------------------------------------------
# STUDIO_DATA_DIR relocates music/, output/ and tmp/ (handy for tests or
# keeping media on a separate disk). Defaults to the project folder.
DATA_DIR: Path = _env_path("STUDIO_DATA_DIR", PROJECT_DIR)
MUSIC_DIR: Path = _env_path("MUSIC_DIR", DATA_DIR / "music")
OUTPUT_DIR: Path = DATA_DIR / "output"
TMP_DIR: Path = DATA_DIR / "tmp"
SOURCES_DIR: Path = TMP_DIR / "sources"   # downloaded YouTube sources
WORK_DIR: Path = TMP_DIR / "work"         # intermediate clips / overlays
UPLOAD_DIR: Path = TMP_DIR / "uploads"    # user uploads (videos, voice)
ASSETS_DIR: Path = PROJECT_DIR / "assets"

TEMP_MAX_AGE_HOURS: int = 24

# --- Video format ---------------------------------------------------------
OUT_W: int = 1080
OUT_H: int = 1920
FPS: int = 30
TRANSITION_SECONDS: float = 0.4

MIN_DURATION: int = 7
MAX_DURATION: int = 25
MAX_CLIPS: int = 15
MAX_SOURCE_SECONDS: int = 15 * 60  # longer YouTube sources are skipped

# --- Audio ----------------------------------------------------------------
AUDIO_RATE: int = 44100
DUCK_VOLUME: float = 0.13          # music level under a voiceover (12–15 %)

# --- Fonts (Pillow overlays; Cyrillic needs DejaVu or Arial) ---------------
BOLD_FONT_CANDIDATES: tuple[str, ...] = (
    os.getenv("FONT_PATH", ""),
    str(ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
EMOJI_FONT_CANDIDATES: tuple[str, ...] = (
    os.getenv("EMOJI_FONT_PATH", ""),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf",
    "/Library/Fonts/Apple Color Emoji.ttc",
    "C:/Windows/Fonts/seguiemj.ttf",
)

# Vertical-video framing modes
FRAMING_BLUR = "blur"
FRAMING_CROP = "crop"
FRAMING_LABELS: dict[str, str] = {
    FRAMING_BLUR: "Умный 9:16 с размытым фоном (Blur Background)",
    FRAMING_CROP: "Полный экран (Center Crop 9:16)",
}


def ffmpeg_source() -> str:
    """Human-readable description of which ffmpeg binary is used."""
    return "системный ffmpeg" if shutil.which("ffmpeg") else "imageio-ffmpeg"


def ensure_dirs() -> None:
    for folder in (MUSIC_DIR, OUTPUT_DIR, SOURCES_DIR, WORK_DIR, UPLOAD_DIR):
        folder.mkdir(parents=True, exist_ok=True)
