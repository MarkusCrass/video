"""Tab 2: trim, 9:16 framing, text overlay, voiceover with auto-ducking."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import streamlit as st

from studio import config, music, storage, textart
from studio.editor import EditError, EditOptions, render_edit
from studio.ui.common import duration_of, fmt_bytes, save_bytes_once

log = logging.getLogger("studio.ui.editor")

VIDEO_TYPES = ["mp4", "mov", "m4v"]
AUDIO_TYPES = ["mp3", "m4a", "wav", "ogg"]


def _source_selector() -> Path | None:
    st.markdown("#### 🎞️ Исходное видео")
    mode = st.radio(
        "Источник",
        ["gen", "upload"],
        key="ed_mode",
        format_func=lambda k: "🎬 Ролик из генератора" if k == "gen" else "📁 Загрузить свой файл (MP4/MOV)",
        horizontal=True,
    )
    if mode == "gen":
        outputs = storage.list_outputs()
        names = [p.name for p in outputs]
        if not names:
            st.info("Готовых роликов пока нет. Сгенерируйте их на вкладке 🎬 или загрузите свой файл.")
            return None
        if st.session_state.get("ed_pick") not in names:
            st.session_state["ed_pick"] = names[0]
        st.selectbox("Ролик", names, key="ed_pick")
        return config.OUTPUT_DIR / st.session_state["ed_pick"]

    uploaded = st.file_uploader("Видео с телефона или ПК", type=VIDEO_TYPES, key="ed_upload")
    if uploaded is None:
        st.info("Выберите файл MP4 или MOV.")
        return None
    signature = (uploaded.name, uploaded.size)
    if st.session_state.get("ed_upload_sig") != signature:
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = config.UPLOAD_DIR / f"src_{uploaded.file_id}_{Path(uploaded.name).name}"
        target.write_bytes(uploaded.getvalue())
        st.session_state["ed_upload_sig"] = signature
        st.session_state["ed_upload_path"] = str(target)
    return Path(st.session_state["ed_upload_path"])


def _trim_controls(src: Path) -> tuple[float, float] | None:
    total = duration_of(src)
    if total < 1:
        st.error("Не удалось определить длительность видео.")
        return None
    st.markdown("#### ✂️ Обрезка")
    st.caption(f"Длительность исходника: {total:.1f} с")
    key = "ed_trim_" + hashlib.md5(str(src).encode("utf-8")).hexdigest()[:10]
    start, end = st.slider(
        "Начало и конец фрагмента (сек)", 0.0, round(total, 1),
        (0.0, round(total, 1)), step=0.1, key=key,
    )
    st.caption(f"Длина фрагмента: {end - start:.1f} с")
    return float(start), float(end)


def _text_controls() -> None:
    st.markdown("#### 🖋️ Текст на экране")
    st.text_input("Заголовок сверху", key="ed_top", placeholder="Знаки Луны героинь 🌙")
    st.text_input("Текст по центру", key="ed_center", placeholder="Например: Ждите финал!")
    st.text_input("Призыв внизу (CTA)", key="ed_bottom", placeholder="Пиши ЛУНА в комментарии 👇")
    c1, c2 = st.columns(2)
    c1.selectbox("Цвет и стиль", list(textart.STYLES), key="ed_style",
                 format_func=lambda k: textart.STYLE_LABELS[k])
    c2.select_slider("Размер шрифта", options=list(textart.SIZE_SCALES), key="ed_size")
    if not textart.EMOJI_AVAILABLE:
        st.caption("ℹ️ Эмодзи пропускаются без шрифта fonts-noto-color-emoji.")


def _voice_controls() -> Path | None:
    st.markdown("#### 🎙️ Озвучка (Voiceover)")
    recording = st.audio_input("Записать голос с микрофона", key="ed_voice_rec")
    voice_file = st.file_uploader("…или загрузить готовую запись (диктофон)", type=AUDIO_TYPES,
                                  key="ed_voice_file")
    voice_path = None
    if voice_file is not None:
        voice_path = save_bytes_once(voice_file.getvalue(), "." + voice_file.name.rsplit(".", 1)[-1], "voice")
    elif recording is not None:
        voice_path = save_bytes_once(recording.getvalue(), ".wav", "voice")
    if voice_path is not None:
        st.success(f"Голос подключён: {voice_path.name} · {duration_of(voice_path):.1f} с · громкость 100 %")
    return voice_path


def _mix_controls(has_voice: bool) -> tuple[Path | None, float, float, float]:
    st.markdown("#### 🎵 Музыка и звук")
    tracks = music.list_tracks()
    options = [music.MUSIC_NONE] + [t.name for t in tracks]
    if st.session_state.get("ed_music") not in options:
        st.session_state["ed_music"] = music.MUSIC_NONE
    st.selectbox("Фоновая музыка", options, key="ed_music",
                 format_func=lambda k: "🔇 Без музыки" if k == music.MUSIC_NONE else f"🎵 {k}")
    c1, c2 = st.columns(2)
    if has_voice:
        c1.slider("Музыка под голосом (авто-приглушение)", 12, 15, key="ed_duck", format="%d%%",
                  help="Во время озвучки музыка автоматически приглушается до 12–15 %.")
        c2.slider("Звук видео (оригинал)", 0, 100, key="ed_orig", format="%d%%",
                  help="Обычно при озвучке оставляют 0–20 %, чтобы голос не конкурировал со звуком.")
        music_vol = 0.0
        duck = st.session_state["ed_duck"] / 100
    else:
        c1.slider("Громкость музыки", 0, 100, key="ed_music_vol", format="%d%%")
        c2.slider("Громкость звука видео", 0, 100, key="ed_orig", format="%d%%")
        music_vol = st.session_state["ed_music_vol"] / 100
        duck = config.DUCK_VOLUME
    chosen = None if st.session_state["ed_music"] == music.MUSIC_NONE else config.MUSIC_DIR / st.session_state["ed_music"]
    return chosen, music_vol, duck, st.session_state["ed_orig"] / 100


def _ensure_defaults() -> None:
    defaults = {
        "ed_mode": "gen", "ed_top": "", "ed_center": "", "ed_bottom": "",
        "ed_style": "white", "ed_size": "M", "ed_music": music.MUSIC_NONE,
        "ed_music_vol": 30, "ed_duck": 13, "ed_orig": 100, "ed_framing": config.FRAMING_BLUR,
        "ed_soft": False, "ed_result": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render() -> None:
    _ensure_defaults()
    st.markdown("### ✂️ Студия монтажа и озвучки (Редактор видео)")
    st.caption("Доработайте любой ролик или своё видео: обрежьте, добавьте голос, текст и музыку.")
    if flash := st.session_state.pop("ed_flash", None):
        st.success(flash)

    src = _source_selector()
    if src is None:
        return
    if not src.is_file():
        st.error("Файл не найден. Выберите другой ролик.")
        return

    st.video(str(src))
    trim = _trim_controls(src)
    if trim is None:
        return

    st.markdown("#### 📐 Кадрирование")
    st.radio("Режим 9:16", list(config.FRAMING_LABELS), key="ed_framing",
             format_func=lambda k: config.FRAMING_LABELS[k], label_visibility="collapsed")
    _text_controls()
    voice = _voice_controls()
    music_path, music_vol, duck, orig_vol = _mix_controls(voice is not None)
    st.checkbox("Плавное появление и затухание", key="ed_soft")

    st.divider()
    if st.button("✨ Собрать финальный ролик", type="primary", width="stretch"):
        _run_render(src, trim, voice, music_path, music_vol, duck, orig_vol)

    result: Path | None = st.session_state.get("ed_result")
    if result and result.is_file():
        st.markdown("#### 📱 Результат · 1080×1920")
        with st.container(border=True):
            st.video(str(result))
            st.caption(f"{result.name} · {fmt_bytes(result.stat().st_size)}")
            st.download_button("⬇️ Скачать MP4", data=result.read_bytes(), file_name=result.name,
                               mime="video/mp4", type="primary", width="stretch", key="ed_dl")


def _run_render(src: Path, trim, voice, music_path, music_vol, duck, orig_vol) -> None:
    opts = EditOptions(
        start=trim[0],
        end=trim[1],
        framing=st.session_state["ed_framing"],
        orig_volume=orig_vol,
        music_path=music_path,
        music_volume=music_vol,
        duck_volume=duck,
        voice_path=voice,
        top_text=st.session_state["ed_top"],
        center_text=st.session_state["ed_center"],
        bottom_text=st.session_state["ed_bottom"],
        text_style=st.session_state["ed_style"],
        text_size=st.session_state["ed_size"],
        soft_edges=bool(st.session_state["ed_soft"]),
    )
    bar = st.progress(0.0, text="Подготовка…")
    try:
        out = render_edit(src, opts, progress=lambda f, t: bar.progress(min(1.0, f), text=t))
    except EditError as exc:
        bar.empty()
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Edit render failed")
        bar.empty()
        st.error(f"Ошибка монтажа: {exc}")
        return
    st.session_state["ed_result"] = out
    st.toast("Ролик готов", icon="✨")
