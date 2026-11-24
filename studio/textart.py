"""Text overlays rendered with Pillow as transparent PNG (1080x1920).

Rendering text in Pillow instead of ffmpeg `drawtext` avoids font-path,
escaping and line-break problems on every OS. Emoji are drawn from a colour
emoji font when one is installed (fonts-noto-color-emoji); otherwise they are
dropped so that the text never shows empty boxes.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from studio import config

STYLES: dict[str, dict] = {
    "white": {"text": (255, 255, 255, 255), "box": (0, 0, 0, 150)},
    "gold": {"text": (255, 209, 102, 255), "box": (0, 0, 0, 165)},
    "black": {"text": (17, 17, 17, 255), "box": (255, 255, 255, 235)},
}
STYLE_LABELS: dict[str, str] = {
    "white": "Белый на тёмной подложке",
    "gold": "Золотой на тёмной подложке",
    "black": "Чёрный на белой плашке",
}
SIZE_SCALES: dict[str, float] = {"S": 0.8, "M": 1.0, "L": 1.25}

# Codepoints treated as emoji (pictographs, symbols, flags, keycaps).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF\u2190-\u21FF"
    "\u00A9\u00AE\u203C\u2049\u2122\u2139\u3030\u303D\u3297\u3299]"
)
_IGNORED = {"\ufe0f", "\ufe0e", "\u200d", "\u20e3"}  # variation selectors, ZWJ, keycap
_NON_BMP_MIN = 0x1F000

_BASE_SIZES = {"top": 64, "center": 92, "bottom": 60}
_MARGIN_X = 90


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in config.BOLD_FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise FileNotFoundError(
        "Шрифт DejaVuSans-Bold.ttf не найден. Положите его в assets/fonts/ "
        "или установите пакет fonts-dejavu-core."
    )


def _emoji_font_path() -> str | None:
    for candidate in config.EMOJI_FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


EMOJI_FONT_PATH = _emoji_font_path()
EMOJI_AVAILABLE = EMOJI_FONT_PATH is not None


@lru_cache(maxsize=512)
def _emoji_glyph(char: str, target_px: int) -> Image.Image | None:
    if not EMOJI_FONT_PATH:
        return None
    try:
        font = ImageFont.truetype(EMOJI_FONT_PATH, 109)
    except OSError:
        return None
    canvas = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((10, 10), char, font=font, embedded_color=True)
    box = canvas.getbbox()
    if not box:
        return None
    glyph = canvas.crop(box)
    scale = target_px / max(glyph.size)
    size = (max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale)))
    return glyph.resize(size, Image.LANCZOS)


def _segments(text: str) -> list[tuple[str, str]]:
    """Split text into ('text', str) and ('emoji', char) runs.

    Without an emoji font, pictographs (non-BMP) and the 2B00-2BFF block are
    dropped so the overlay never shows empty squares.
    """
    segments: list[tuple[str, str]] = []
    buffer = ""
    for char in text:
        if char in _IGNORED:
            continue
        is_emoji = bool(_EMOJI_RE.fullmatch(char))
        if is_emoji and not EMOJI_AVAILABLE:
            if ord(char) >= _NON_BMP_MIN or 0x2B00 <= ord(char) <= 0x2BFF:
                continue
            is_emoji = False
        if is_emoji:
            if buffer:
                segments.append(("text", buffer))
                buffer = ""
            segments.append(("emoji", char))
        else:
            buffer += char
    if buffer:
        segments.append(("text", buffer))
    return segments


def _seg_width(seg: tuple[str, str], font: ImageFont.FreeTypeFont, px: int) -> float:
    kind, value = seg
    return font.getlength(value) if kind == "text" else px * 1.1


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int, px: int) -> list[list[tuple[str, str]]]:
    """Word-wrap `text` into lines of segments, honouring explicit newlines."""
    lines: list[list[tuple[str, str]]] = []
    space_w = font.getlength(" ")
    for paragraph in text.split("\n"):
        words = [w for w in paragraph.split(" ") if w]
        if not words:
            lines.append([])
            continue
        current: list[tuple[str, str]] = []
        width = 0.0
        for word in words:
            word_segs = _segments(word)
            word_w = sum(_seg_width(s, font, px) for s in word_segs)
            if not word_segs:
                continue
            add = word_w if not current else space_w + word_w
            if current and width + add > max_width:
                lines.append(current)
                current, width = [], 0.0
                add = word_w
            if current:
                current.append(("text", " "))
            current.extend(word_segs)
            width += add
        if current:
            lines.append(current)
    return lines


def _line_width(line: list[tuple[str, str]], font: ImageFont.FreeTypeFont, px: int) -> float:
    return sum(_seg_width(s, font, px) for s in line)


def _render_block(text: str, base_size: int, style: str, scale: float, max_width: int) -> Image.Image | None:
    if not text or not text.strip():
        return None
    palette = STYLES[style]
    px = max(12, round(base_size * scale))
    font = _font(px)
    pad_x, pad_y = round(px * 0.55), round(px * 0.42)
    line_h = round(px * 1.22)
    lines = _wrap(text.strip(), font, max_width - 2 * pad_x, px)
    lines = [line for line in lines if line] or []
    if not lines:
        return None
    widths = [_line_width(line, font, px) for line in lines]
    block_w = int(max(widths) + 2 * pad_x)
    block_h = int(line_h * len(lines) + 2 * pad_y)
    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)
    radius = round(px * 0.4)
    draw.rounded_rectangle((0, 0, block_w - 1, block_h - 1), radius=radius, fill=palette["box"])
    for index, (line, width) in enumerate(zip(lines, widths)):
        x = (block_w - width) / 2
        y = pad_y + index * line_h
        for seg in line:
            kind, value = seg
            if kind == "text":
                draw.text((x, y), value, font=font, fill=palette["text"])
                x += font.getlength(value)
            else:
                glyph = _emoji_glyph(value, round(px * 1.05))
                if glyph is not None:
                    block.alpha_composite(glyph, (round(x), round(y + (line_h - glyph.height) / 2)))
                x += px * 1.1
    return block


def render_overlay(
    out_path: Path,
    *,
    top: str = "",
    center: str = "",
    bottom: str = "",
    style: str = "white",
    size: str = "M",
    width: int = config.OUT_W,
    height: int = config.OUT_H,
) -> Path:
    """Render title (top), centre text and CTA (bottom) into one transparent PNG."""
    if style not in STYLES:
        raise ValueError(f"Неизвестный стиль текста: {style}")
    scale = SIZE_SCALES.get(size, 1.0)
    max_w = width - 2 * _MARGIN_X
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    top_img = _render_block(top, _BASE_SIZES["top"], style, scale, max_w)
    if top_img is not None:
        canvas.alpha_composite(top_img, ((width - top_img.width) // 2, 170))

    center_img = _render_block(center, _BASE_SIZES["center"], style, scale, max_w)
    if center_img is not None:
        canvas.alpha_composite(center_img, ((width - center_img.width) // 2, (height - center_img.height) // 2))

    bottom_img = _render_block(bottom, _BASE_SIZES["bottom"], style, scale, max_w)
    if bottom_img is not None:
        # Keep clear of the platform UI (like/comment/caption bar).
        y = height - 380 - bottom_img.height
        canvas.alpha_composite(bottom_img, ((width - bottom_img.width) // 2, max(0, y)))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path


def preview_text(text: str) -> str:
    """Text as it will be drawn (emoji removed when no emoji font is installed)."""
    return " ".join("".join(value for _, value in _segments(text or "")).split())


def has_emoji(text: str) -> bool:
    return any(_EMOJI_RE.fullmatch(ch) for ch in (text or "") if ch not in _IGNORED)
