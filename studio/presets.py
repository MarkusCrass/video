"""One-click presets for the batch generator."""

from __future__ import annotations

from dataclasses import dataclass

from studio import config
from studio.renderer import TRANSITION_CUT, TRANSITION_FADE


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    hint: str
    query: str
    count: int
    duration: int
    scenes: int
    transition: str
    framing: str
    zoom: bool
    soft_edges: bool
    music_volume: int   # percent
    orig_volume: int    # percent


PRESETS: tuple[Preset, ...] = (
    Preset(
        key="astro",
        title="🌙 Астрология и эстетика (под голос девушки)",
        hint="Тихий фон музыки 15 %, плавный зум 9:16, без резких склеек, мягкие fade-in/out.",
        query="aesthetic full moon night sky vertical",
        count=3, duration=15, scenes=1, transition=TRANSITION_FADE,
        framing=config.FRAMING_CROP, zoom=True, soft_edges=True,
        music_volume=15, orig_volume=100,
    ),
    Preset(
        key="series",
        title="🎭 Разбор сериалов (4 сцены по 3.5 сек)",
        hint="4 динамичных момента по 3.5 с = ролик 14 с. Фон музыки 15 %, кадр не обрезает лица.",
        query="Отчаянные домохозяйки лучшие моменты",
        count=3, duration=14, scenes=4, transition=TRANSITION_CUT,
        framing=config.FRAMING_BLUR, zoom=False, soft_edges=False,
        music_volume=15, orig_volume=100,
    ),
    Preset(
        key="games",
        title="🔥 Игровые хайлайты (CS2 / Dota 2)",
        hint="Агрессивная динамика: 3 резких склейки, трек 100 %, звук игры 15 %, UI не обрезается.",
        query="CS2 clutch highlights",
        count=3, duration=15, scenes=3, transition=TRANSITION_CUT,
        framing=config.FRAMING_BLUR, zoom=False, soft_edges=False,
        music_volume=100, orig_volume=15,
    ),
)


def preset_by_key(key: str) -> Preset:
    for preset in PRESETS:
        if preset.key == key:
            return preset
    raise KeyError(key)
