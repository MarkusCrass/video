"""Music library (`music/` folder): listing, saving uploads, deleting, random pick."""

from __future__ import annotations

import random
import re
from pathlib import Path

from studio import config

AUDIO_EXTS = (".mp3", ".wav")
_SAFE_RE = re.compile(r"[^A-Za-zА-Яа-яЁё0-9 ._()\-\[\]]+")


def list_tracks() -> list[Path]:
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    tracks = [p for p in config.MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    return sorted(tracks, key=lambda p: p.name.lower())


def safe_filename(name: str) -> str:
    """Keep letters (incl. Cyrillic), digits and a few symbols; enforce audio extension."""
    path = Path(name)
    ext = path.suffix.lower()
    stem = _SAFE_RE.sub("_", path.stem).strip(" ._") or "track"
    if ext not in AUDIO_EXTS:
        ext = ".mp3"
    return f"{stem[:120]}{ext}"


def save_track(name: str, data: bytes) -> Path:
    """Write uploaded bytes into the library; never overwrites (adds ' (2)' etc.)."""
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    base = safe_filename(name)
    target = config.MUSIC_DIR / base
    counter = 2
    while target.exists():
        target = config.MUSIC_DIR / f"{Path(base).stem} ({counter}){Path(base).suffix}"
        counter += 1
    target.write_bytes(data)
    return target


def delete_track(name: str) -> bool:
    path = (config.MUSIC_DIR / Path(name).name).resolve()
    if path.parent != config.MUSIC_DIR.resolve() or not path.is_file():
        return False
    path.unlink()
    return True


def random_track(rng: random.Random | None = None) -> Path | None:
    tracks = list_tracks()
    if not tracks:
        return None
    return (rng or random).choice(tracks)


MUSIC_RANDOM = "__random__"   # pick a random track from the library
MUSIC_NONE = "__none__"       # no background music


def resolve_track(choice: str, rng: random.Random | None = None) -> Path | None:
    """Map a UI choice (random / none / file name) to a library file or None."""
    if choice == MUSIC_NONE:
        return None
    if choice == MUSIC_RANDOM:
        return random_track(rng)
    path = config.MUSIC_DIR / Path(choice).name
    return path if path.is_file() else None
