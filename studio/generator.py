"""Batch generator: search YouTube -> download sources -> cut 9:16 reels.

Stages reported to the UI:
  * "Скачивание i/N..."  – search results are tried in order; unavailable or
    too long (> 15 min) videos are skipped and the next result is used.
  * "Монтаж i/N..."      – each source becomes one vertical reel.
"""

from __future__ import annotations

import logging
import random
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from studio import config, music, renderer, textart, youtube
from studio.ffmpeg_tools import FFmpegError, detect_cut_points, ffmpeg_path, probe

log = logging.getLogger("studio.generator")
ProgressFn = Callable[[float, str], None]
LogFn = Callable[[str], None]


class GenerationError(RuntimeError):
    """Batch could not produce any video (message is shown to the user)."""


@dataclass
class BatchOptions:
    query: str
    count: int = 3
    duration: int = 15
    scenes: int = 1
    transition: str = renderer.TRANSITION_CUT
    framing: str = config.FRAMING_BLUR
    zoom: bool = False
    soft_edges: bool = False
    music_choice: str = music.MUSIC_RANDOM
    music_volume: float = 0.15
    orig_volume: float = 1.0
    top_text: str = ""
    bottom_text: str = ""
    text_style: str = "white"
    text_size: str = "M"

    def validate(self) -> None:
        if not self.query.strip():
            raise GenerationError("Введите поисковый запрос")
        if not 1 <= self.count <= config.MAX_CLIPS:
            raise GenerationError(f"Количество видео: от 1 до {config.MAX_CLIPS}")
        if not config.MIN_DURATION <= self.duration <= config.MAX_DURATION:
            raise GenerationError(
                f"Длительность: от {config.MIN_DURATION} до {config.MAX_DURATION} сек"
            )
        if not 1 <= self.scenes <= 4:
            raise GenerationError("Количество сцен: от 1 до 4")
        if self.framing not in (config.FRAMING_BLUR, config.FRAMING_CROP):
            raise GenerationError("Неизвестный режим кадрирования")
        if self.scenes > 1 and self.duration / self.scenes < 2:
            raise GenerationError("Слишком короткие сцены: увеличьте длительность или уменьшите число сцен")


@dataclass
class OutputItem:
    path: Path
    index: int
    source_title: str
    source_url: str
    duration: float
    music_name: str | None


@dataclass
class BatchResult:
    items: list[OutputItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _noop_progress(_: float, __: str) -> None:
    return None


def _emit(log_fn: LogFn | None, message: str) -> None:
    log.info(message)
    if log_fn:
        log_fn(message)


def _render_one(
    index: int,
    src: dict,
    opts: BatchOptions,
    total: float,
    seg_len: float,
    overlay_png: Path | None,
    work_dir: Path,
    rng: random.Random,
    music_info: dict[Path, float],
) -> OutputItem:
    """Cut the scenes of one source, join them, add text/music and export."""
    info, cand = src["info"], src["cand"]
    starts = renderer.pick_segments(info.duration, opts.scenes, seg_len, src["cuts"], rng)
    clips: list[Path] = []
    try:
        for scene_no, start in enumerate(starts, start=1):
            clip = work_dir / f"reel{index:02d}_scene{scene_no}.mp4"
            renderer.build_scene_clip(
                src["path"], start, seg_len, clip,
                framing=opts.framing, zoom=opts.zoom,
                orig_volume=opts.orig_volume, has_audio=info.has_audio,
            )
            clips.append(clip)

        track = music.resolve_track(opts.music_choice, rng)
        offset = 0.0
        if track is not None:
            if track not in music_info:
                try:
                    music_info[track] = probe(track).duration
                except FFmpegError:
                    music_info[track] = 0.0
            room = music_info[track] - total - 1
            offset = rng.uniform(0, room) if room > 0 else 0.0

        out = config.OUTPUT_DIR / f"reel_{time.strftime('%Y%m%d_%H%M%S')}_{work_dir.name}_{index:02d}.mp4"
        renderer.compose_final(
            clips, [seg_len] * len(clips), out,
            total=total,
            overlay_png=overlay_png,
            transition=opts.transition,
            music=track, music_gain=opts.music_volume, music_offset=offset,
            soft_edges=opts.soft_edges,
        )
        return OutputItem(
            path=out, index=index, source_title=cand.title,
            source_url=cand.url, duration=total,
            music_name=track.name if track else None,
        )
    finally:
        for clip in clips:
            clip.unlink(missing_ok=True)


def generate_batch(
    opts: BatchOptions,
    progress: ProgressFn | None = None,
    log_fn: LogFn | None = None,
    rng: random.Random | None = None,
) -> BatchResult:
    """Run the full pipeline and return the finished reels (or raise GenerationError)."""
    opts.validate()
    progress = progress or _noop_progress
    rng = rng or random.Random()
    config.ensure_dirs()
    result = BatchResult()
    job = uuid.uuid4().hex[:8]
    src_dir = config.SOURCES_DIR / job
    work_dir = config.WORK_DIR / job
    total = float(opts.duration)
    seg_len = renderer.scene_length(total, opts.scenes, opts.transition)
    min_source = total + 3

    try:
        # ---------------- 1. search ---------------------------------------
        progress(0.02, "Поиск роликов на YouTube…")
        limit = min(40, max(6, opts.count * 4))
        try:
            candidates = youtube.search(opts.query, limit)
        except youtube.YouTubeError as exc:
            raise GenerationError(str(exc)) from exc
        usable = [c for c in candidates if youtube.is_usable(c, min_source)]
        skipped_long = sum(1 for c in candidates if c.duration and c.duration > config.MAX_SOURCE_SECONDS)
        _emit(log_fn, f"Найдено результатов: {len(candidates)}, подходящих по длительности: {len(usable)}")
        if skipped_long:
            result.notes.append(f"Пропущено слишком длинных роликов (> 15 мин): {skipped_long}")
        if not usable:
            raise GenerationError("Подходящих роликов не найдено. Попробуйте другой запрос.")

        # ---------------- 2. download -------------------------------------
        sources: list[dict] = []
        ffmpeg_loc = ffmpeg_path()
        for cand in usable:
            if len(sources) >= opts.count:
                break
            n = len(sources) + 1
            progress(0.05 + 0.4 * (len(sources) / opts.count), f"Скачивание {n}/{opts.count}...")
            try:
                path = youtube.download(cand.url, src_dir / f"src_{n:02d}_{cand.video_id}", ffmpeg_loc)
            except youtube.YouTubeError as exc:
                _emit(log_fn, f"Пропуск «{cand.title[:60]}»: {exc}")
                continue
            try:
                info = probe(path)
            except FFmpegError as exc:
                _emit(log_fn, f"Пропуск «{cand.title[:60]}»: повреждённый файл ({exc})")
                path.unlink(missing_ok=True)
                continue
            if info.duration < min_source or info.duration > config.MAX_SOURCE_SECONDS or not info.has_video:
                _emit(log_fn, f"Пропуск «{cand.title[:60]}»: длительность {info.duration:.0f} с не подходит")
                path.unlink(missing_ok=True)
                continue
            cut_points: list[float] = []
            if opts.scenes > 1:
                cut_points = detect_cut_points(path, max_seconds=min(info.duration, config.MAX_SOURCE_SECONDS))
            sources.append({"path": path, "info": info, "cand": cand, "cuts": cut_points})
            _emit(log_fn, f"Скачано {len(sources)}/{opts.count}: {cand.title[:80]}")

        if not sources:
            raise GenerationError("Не удалось скачать ни одного ролика. Попробуйте позже или другой запрос.")
        if len(sources) < opts.count:
            result.notes.append(f"Удалось скачать {len(sources)} из {opts.count} — собрано столько роликов.")

        # ---------------- 3. overlay + music -------------------------------
        overlay_png = None
        if opts.top_text.strip() or opts.bottom_text.strip():
            overlay_png = textart.render_overlay(
                work_dir / "overlay.png",
                top=opts.top_text, bottom=opts.bottom_text,
                style=opts.text_style, size=opts.text_size,
            )
            if textart.has_emoji(opts.top_text + opts.bottom_text) and not textart.EMOJI_AVAILABLE:
                result.notes.append("Эмодзи в тексте пропущены: установите пакет fonts-noto-color-emoji.")

        music_info: dict[Path, float] = {}

        # ---------------- 4. montage ---------------------------------------
        for index, src in enumerate(sources, start=1):
            progress(0.45 + 0.53 * ((index - 1) / len(sources)), f"Монтаж {index}/{len(sources)}...")
            cand = src["cand"]
            try:
                item = _render_one(
                    index, src, opts, total, seg_len, overlay_png, work_dir, rng, music_info,
                )
            except FFmpegError as exc:
                _emit(log_fn, f"Монтаж {index} не удался ({cand.title[:50]}): {exc}")
                result.notes.append(f"Ролик {index} пропущен из-за ошибки монтажа.")
                continue
            result.items.append(item)
            _emit(log_fn, f"Готово {index}/{len(sources)}: {item.path.name}")

        if not result.items:
            raise GenerationError("Ни один ролик не удалось смонтировать. Подробности — в журнале.")
        progress(1.0, "Готово")
        return result
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
