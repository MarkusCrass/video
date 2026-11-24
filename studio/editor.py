"""Video editor back-end: trim, 9:16 framing, text overlay and voiceover mix."""

from __future__ import annotations

import random
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from studio import config, renderer, textart
from studio.ffmpeg_tools import FFmpegError, probe


class EditError(RuntimeError):
    """User-facing editing error."""


@dataclass
class EditOptions:
    start: float = 0.0
    end: float | None = None          # None = until the end of the source
    framing: str = config.FRAMING_BLUR
    orig_volume: float = 1.0          # 0..1 (original sound of the video)
    music_path: Path | None = None
    music_volume: float = 0.30        # 0..1, used when there is no voiceover
    duck_volume: float = config.DUCK_VOLUME  # 0..1, music level under the voice
    voice_path: Path | None = None
    voice_volume: float = 1.0
    top_text: str = ""
    center_text: str = ""
    bottom_text: str = ""
    text_style: str = "white"
    text_size: str = "M"
    soft_edges: bool = False


def _probe_safely(path: Path):
    try:
        return probe(path)
    except FFmpegError as exc:
        raise EditError(f"Не удалось открыть файл «{path.name}»: {exc}") from exc


def source_duration(path: Path) -> float:
    return _probe_safely(Path(path)).duration


def render_edit(
    src: Path,
    opts: EditOptions,
    progress=None,
    rng: random.Random | None = None,
) -> Path:
    """Render the edited 1080x1920 MP4 into the output folder and return its path."""
    progress = progress or (lambda _p, _m: None)
    rng = rng or random.Random()
    config.ensure_dirs()
    src = Path(src)
    info = _probe_safely(src)
    if not info.has_video:
        raise EditError("В файле нет видеодорожки")
    end = info.duration if opts.end is None else min(opts.end, info.duration)
    start = max(0.0, opts.start)
    length = end - start
    if length < 1.0:
        raise EditError("Фрагмент слишком короткий: выберите минимум 1 секунду")
    if opts.voice_path is not None:
        voice_len = _probe_safely(opts.voice_path).duration
        if voice_len <= 0:
            raise EditError("Не удалось прочитать аудио озвучки")

    job = uuid.uuid4().hex[:8]
    work_dir = config.WORK_DIR / f"edit_{job}"
    try:
        progress(0.1, "Обрезка и кадрирование 9:16…")
        clip = renderer.build_scene_clip(
            src, start, length, work_dir / "clip.mp4",
            framing=opts.framing, zoom=False,
            orig_volume=opts.orig_volume, has_audio=info.has_audio,
        )

        overlay = None
        if opts.top_text.strip() or opts.center_text.strip() or opts.bottom_text.strip():
            progress(0.45, "Рисуем текст на экране…")
            overlay = textart.render_overlay(
                work_dir / "overlay.png",
                top=opts.top_text, center=opts.center_text, bottom=opts.bottom_text,
                style=opts.text_style, size=opts.text_size,
            )

        if opts.voice_path is not None:
            music_gain = opts.duck_volume  # auto-ducking under the voiceover
            voice_gain = opts.voice_volume
        else:
            music_gain = opts.music_volume
            voice_gain = 1.0

        offset = 0.0
        if opts.music_path is not None and music_gain > 0:
            music_len = _probe_safely(opts.music_path).duration
            room = music_len - length - 1
            offset = rng.uniform(0, room) if room > 0 else 0.0

        progress(0.6, "Микширование звука и экспорт…")
        out = config.OUTPUT_DIR / f"edit_{time.strftime('%Y%m%d_%H%M%S')}_{job}.mp4"
        renderer.compose_final(
            [clip], [length], out,
            total=length,
            overlay_png=overlay,
            transition=renderer.TRANSITION_CUT,
            music=opts.music_path if music_gain > 0 else None,
            music_gain=music_gain,
            music_offset=offset,
            voice=opts.voice_path,
            voice_gain=voice_gain,
            soft_edges=opts.soft_edges,
        )
        progress(1.0, "Готово")
        return out
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
