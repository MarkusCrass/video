"""Video assembly with ffmpeg: 9:16 framing, scene clips, final mix.

Pipeline
--------
1. `build_scene_clip`  – cut one segment from a source, frame it to 1080x1920
   (blur-background or centre crop), optional slow zoom, normalise audio.
2. `compose_final`     – join scene clips (hard cut or cross-fade), overlay the
   Pillow text PNG, mix original audio + music (+ voiceover with ducking),
   fade edges, encode H.264/AAC MP4.
"""

from __future__ import annotations

import random
from pathlib import Path

from studio import config
from studio.ffmpeg_tools import run_ffmpeg

W, H, FPS = config.OUT_W, config.OUT_H, config.FPS
TRANSITION_CUT = "cut"
TRANSITION_FADE = "fade"
TRANSITION_LABELS = {TRANSITION_CUT: "Резкая склейка", TRANSITION_FADE: "Плавный переход (fade)"}

_ENC_SCENE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS)]
_ENC_FINAL = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
              "-pix_fmt", "yuv420p", "-r", str(FPS)]
_ENC_AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", str(config.AUDIO_RATE), "-ac", "2",
              "-movflags", "+faststart"]


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def framing_filter(framing: str, src: str, dst: str) -> str:
    """filter_complex fragment turning `src` video label into a 1080x1920 `dst` label."""
    if framing == config.FRAMING_CROP:
        return (
            f"[{src}]scale={W}:{H}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={W}:{H},setsar=1[{dst}]"
        )
    if framing == config.FRAMING_BLUR:
        return (
            f"[{src}]split=2[bgs_{dst}][fgs_{dst}];"
            # Blur is computed on a 1/5 scale copy and stretched back: same look, ~5x faster.
            f"[bgs_{dst}]scale={W // 5}:{H // 5}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={W // 5}:{H // 5},boxblur=luma_radius=8:luma_power=3,"
            f"scale={W}:{H}:flags=bicubic,eq=brightness=-0.14:saturation=1.1[bg_{dst}];"
            f"[fgs_{dst}]scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"setsar=1[fg_{dst}];"
            f"[bg_{dst}][fg_{dst}]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[{dst}]"
        )
    raise ValueError(f"Неизвестный режим кадрирования: {framing}")


def build_scene_clip(
    src: Path,
    start: float,
    length: float,
    out_path: Path,
    *,
    framing: str = config.FRAMING_BLUR,
    zoom: bool = False,
    orig_volume: float = 1.0,
    has_audio: bool = True,
) -> Path:
    """Cut `length` seconds starting at `start` and frame them to 9:16."""
    if length <= 0:
        raise ValueError("Длина фрагмента должна быть больше нуля")
    frames = max(1, round(length * FPS))
    chain = [framing_filter(framing, "0:v:0", "fr")]
    if zoom:
        # Slow push-in: +8 % over the clip, centred.
        chain.append(
            f"[fr]zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={W}x{H}:fps={FPS}[zm]"
        )
        video_label = "zm"
    else:
        video_label = "fr"
    chain.append(f"[{video_label}]fps={FPS},format=yuv420p,setsar=1[v]")

    if has_audio:
        chain.append(
            f"[0:a:0]aformat=sample_rates={config.AUDIO_RATE}:channel_layouts=stereo,"
            f"volume={_fmt(max(0.0, orig_volume))}[a]"
        )
        extra_inputs: list[str] = []
    else:
        chain.append(f"[1:a]atrim=0:{_fmt(length)},asetpts=PTS-STARTPTS[a]")
        extra_inputs = ["-f", "lavfi", "-i",
                        f"anullsrc=channel_layout=stereo:sample_rate={config.AUDIO_RATE}"]

    args = ["-ss", _fmt(max(0.0, start)), "-i", str(src), *extra_inputs,
            "-filter_complex", ";".join(chain),
            "-map", "[v]", "-map", "[a]", "-t", _fmt(length),
            *_ENC_SCENE, *_ENC_AUDIO, str(out_path)]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(args)
    return out_path


def compose_final(
    clips: list[Path],
    clip_lengths: list[float],
    out_path: Path,
    *,
    total: float,
    overlay_png: Path | None = None,
    transition: str = TRANSITION_CUT,
    transition_s: float = config.TRANSITION_SECONDS,
    music: Path | None = None,
    music_gain: float = 0.15,
    music_offset: float = 0.0,
    voice: Path | None = None,
    voice_gain: float = 1.0,
    soft_edges: bool = False,
) -> Path:
    """Join clips, overlay text, mix music/voice and encode the final 1080x1920 MP4."""
    if not clips:
        raise ValueError("Нет клипов для сборки")
    if len(clips) != len(clip_lengths):
        raise ValueError("Количество клипов и длительностей не совпадает")
    count = len(clips)
    fade = transition == TRANSITION_FADE and count > 1
    t = transition_s if fade else 0.0

    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    overlay_idx = music_idx = voice_idx = None
    next_idx = count
    if overlay_png:
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(overlay_png)]
        overlay_idx = next_idx
        next_idx += 1
    if music:
        inputs += ["-stream_loop", "-1", "-ss", _fmt(max(0.0, music_offset)), "-i", str(music)]
        music_idx = next_idx
        next_idx += 1
    if voice:
        inputs += ["-i", str(voice)]
        voice_idx = next_idx
        next_idx += 1

    chains: list[str] = []
    # --- video join -------------------------------------------------------
    if count == 1:
        chains.append("[0:v]null[vj]")
    elif fade:
        prev = "[0:v]"
        offset = 0.0
        for i in range(1, count):
            offset += clip_lengths[i - 1] - t
            out = "[vj]" if i == count - 1 else f"[vx{i}]"
            chains.append(f"{prev}[{i}:v]xfade=transition=fade:duration={_fmt(t)}:offset={_fmt(offset)}{out}")
            prev = out
    else:
        labels = "".join(f"[{i}:v]" for i in range(count))
        chains.append(f"{labels}concat=n={count}:v=1:a=0[vj]")

    # --- audio join -------------------------------------------------------
    if count == 1:
        chains.append("[0:a]anull[aj]")
    elif fade:
        prev = "[0:a]"
        for i in range(1, count):
            out = "[aj]" if i == count - 1 else f"[ax{i}]"
            chains.append(f"{prev}[{i}:a]acrossfade=d={_fmt(t)}:c1=tri:c2=tri{out}")
            prev = out
    else:
        labels = "".join(f"[{i}:a]" for i in range(count))
        chains.append(f"{labels}concat=n={count}:v=0:a=1[aj]")

    # --- text overlay -----------------------------------------------------
    if overlay_idx is not None:
        chains.append(f"[vj][{overlay_idx}:v]overlay=0:0:format=auto,format=yuv420p[vo]")
    else:
        chains.append("[vj]format=yuv420p[vo]")

    # --- audio mix --------------------------------------------------------
    mix_inputs = ["[aj]"]
    if music_idx is not None:
        fade_out_at = max(0.0, total - 1.5)
        chains.append(
            f"[{music_idx}:a]atrim=0:{_fmt(total + 0.5)},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates={config.AUDIO_RATE}:channel_layouts=stereo,"
            f"volume={_fmt(max(0.0, music_gain))},afade=t=in:st=0:d=0.6,"
            f"afade=t=out:st={_fmt(fade_out_at)}:d=1.5[mu]"
        )
        mix_inputs.append("[mu]")
    if voice_idx is not None:
        chains.append(
            f"[{voice_idx}:a]aformat=sample_rates={config.AUDIO_RATE}:channel_layouts=stereo,"
            f"volume={_fmt(max(0.0, voice_gain))},atrim=0:{_fmt(total)},"
            f"asetpts=PTS-STARTPTS[vc]"
        )
        mix_inputs.append("[vc]")
    if len(mix_inputs) > 1:
        chains.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:"
            f"dropout_transition=0:normalize=0,alimiter=limit=0.95[am]"
        )
    else:
        chains.append("[aj]anull[am]")

    # --- edge fades -------------------------------------------------------
    if soft_edges and total > 2:
        chains.append(
            f"[vo]fade=t=in:st=0:d=0.5,fade=t=out:st={_fmt(total - 0.6)}:d=0.6[vf]"
        )
        chains.append(
            f"[am]afade=t=in:st=0:d=0.3,afade=t=out:st={_fmt(total - 0.8)}:d=0.8[af]"
        )
    else:
        chains.append("[vo]null[vf]")
        chains.append("[am]anull[af]")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [*inputs, "-filter_complex", ";".join(chains),
            "-map", "[vf]", "-map", "[af]", "-t", _fmt(total),
            *_ENC_FINAL, *_ENC_AUDIO, str(out_path)]
    run_ffmpeg(args, timeout=3600)
    return out_path


def pick_segments(
    source_duration: float,
    count: int,
    seg_len: float,
    cut_points: list[float] | None = None,
    rng: random.Random | None = None,
) -> list[float]:
    """Choose `count` start times (seconds) for segments of `seg_len` seconds.

    Prefers scene-change timestamps (dynamic moments), keeps segments from
    overlapping when possible and skips the first 3 s (usually intros).
    """
    rng = rng or random.Random()
    max_start = source_duration - seg_len
    if max_start < 0:
        raise ValueError("Исходник короче нужного фрагмента")
    low = min(3.0, max_start)
    high = max_start
    chosen: list[float] = []

    candidates = [t for t in (cut_points or []) if low <= t <= high]
    rng.shuffle(candidates)
    for point in candidates:
        if len(chosen) >= count:
            break
        if all(abs(point - c) >= seg_len for c in chosen):
            chosen.append(point)

    attempts = 0
    while len(chosen) < count and attempts < 400:
        attempts += 1
        point = rng.uniform(low, high)
        if all(abs(point - c) >= seg_len for c in chosen):
            chosen.append(point)
    while len(chosen) < count:  # very short source: allow overlap
        chosen.append(rng.uniform(low, high))
    return sorted(round(c, 2) for c in chosen)


def scene_length(total: float, scenes: int, transition: str) -> float:
    """Length of each scene so that the joined clip lasts exactly `total`."""
    if scenes <= 1:
        return total
    if transition == TRANSITION_FADE:
        return (total + (scenes - 1) * config.TRANSITION_SECONDS) / scenes
    return total / scenes
