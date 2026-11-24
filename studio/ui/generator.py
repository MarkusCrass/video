"""Tab 1: one-click presets and the batch generator (1–15 vertical reels)."""

from __future__ import annotations

import logging

import streamlit as st

from studio import config, music, presets, renderer, textart
from studio.generator import BatchOptions, GenerationError, generate_batch

log = logging.getLogger("studio.ui.generator")

DEFAULTS: dict = {
    "g_query": "",
    "g_count": 3,
    "g_duration": 15,
    "g_scenes": 1,
    "g_transition": renderer.TRANSITION_CUT,
    "g_framing": config.FRAMING_BLUR,
    "g_zoom": False,
    "g_soft": False,
    "g_music": music.MUSIC_RANDOM,
    "g_music_vol": 15,
    "g_orig_vol": 100,
    "g_top": "",
    "g_bottom": "",
    "g_style": "white",
    "g_size": "M",
    "g_results": [],
    "g_notes": [],
    "g_logs": [],
}


def _init_defaults() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)


def apply_preset(key: str) -> None:
    """on_click callback: fill every generator control from a preset."""
    preset = presets.preset_by_key(key)
    st.session_state.update({
        "g_query": preset.query,
        "g_count": preset.count,
        "g_duration": preset.duration,
        "g_scenes": preset.scenes,
        "g_transition": preset.transition,
        "g_framing": preset.framing,
        "g_zoom": preset.zoom,
        "g_soft": preset.soft_edges,
        "g_music": music.MUSIC_RANDOM,
        "g_music_vol": preset.music_volume,
        "g_orig_vol": preset.orig_volume,
    })
    st.session_state["g_preset_flash"] = preset.title


def open_in_editor(path_name: str) -> None:
    st.session_state["ed_mode"] = "gen"
    st.session_state["ed_pick"] = path_name
    st.session_state["ed_flash"] = f"Ролик «{path_name}» открыт в редакторе — перейдите на вкладку ✂️"


def _music_options() -> list[str]:
    return [music.MUSIC_RANDOM, music.MUSIC_NONE] + [t.name for t in music.list_tracks()]


def _music_label(token: str) -> str:
    if token == music.MUSIC_RANDOM:
        return "🎲 Случайный трек из библиотеки"
    if token == music.MUSIC_NONE:
        return "🔇 Без музыки"
    return f"🎵 {token}"


def _render_presets() -> None:
    st.markdown("#### ⚡ Быстрые пресеты")
    st.caption("Один клик заполняет оптимальные настройки. Их можно поправить вручную ниже.")
    cols = st.columns(len(presets.PRESETS))
    for col, preset in zip(cols, presets.PRESETS):
        with col.container(border=True):
            st.markdown(f"**{preset.title}**")
            st.markdown(f"<div class='preset-hint'>{preset.hint}</div>", unsafe_allow_html=True)
            st.button("Применить пресет", key=f"preset_{preset.key}", width="stretch",
                      on_click=apply_preset, args=(preset.key,))
    if flash := st.session_state.pop("g_preset_flash", None):
        st.success(f"Пресет применён: {flash}")


def _render_controls() -> None:
    st.markdown("#### 🔎 Поиск и параметры")
    st.text_input("Поисковый запрос (русский или английский)", key="g_query",
                  placeholder="Например: Отчаянные домохозяйки лучшие моменты  /  aesthetic full moon night sky vertical")
    c1, c2 = st.columns(2)
    c1.slider("Количество видео", 1, config.MAX_CLIPS, key="g_count")
    c2.slider("Длительность одного ролика (сек)", config.MIN_DURATION, config.MAX_DURATION, key="g_duration")
    c3, c4 = st.columns(2)
    c3.slider("Сцен (склеек) в ролике", 1, 4, key="g_scenes",
              help="Несколько сцен — короткие динамичные моменты из одного видео.")
    c4.radio("Переход между сценами", list(renderer.TRANSITION_LABELS), key="g_transition",
             format_func=lambda k: renderer.TRANSITION_LABELS[k], horizontal=True)

    st.markdown("**Режим кадрирования 9:16 (1080×1920)**")
    st.radio("Кадрирование", list(config.FRAMING_LABELS), key="g_framing",
             format_func=lambda k: config.FRAMING_LABELS[k], label_visibility="collapsed")
    z1, z2 = st.columns(2)
    z1.checkbox("Плавный зум (push-in)", key="g_zoom")
    z2.checkbox("Плавное появление и затухание", key="g_soft")

    st.markdown("**🎵 Музыка и звук**")
    options = _music_options()
    if st.session_state.get("g_music") not in options:
        st.session_state["g_music"] = music.MUSIC_RANDOM
    st.selectbox("Трек из библиотеки", options, key="g_music", format_func=_music_label)
    if not music.list_tracks():
        st.caption("Библиотека пуста — ролики будут без музыки. Добавьте треки на вкладке 🎵.")
    v1, v2 = st.columns(2)
    v1.slider("Громкость музыки", 0, 100, key="g_music_vol", format="%d%%")
    v2.slider("Громкость звука видео", 0, 100, key="g_orig_vol", format="%d%%")

    st.markdown("**🖋️ Текст на экране (необязательно)**")
    st.text_input("Заголовок сверху", key="g_top", placeholder="Знаки Луны героинь из Отчаянных домохозяек 🌙")
    st.text_input("Призыв внизу (CTA)", key="g_bottom", placeholder="Пиши ЛУНА в комментарии 👇")
    t1, t2 = st.columns(2)
    t1.selectbox("Стиль текста", list(textart.STYLES), key="g_style",
                 format_func=lambda k: textart.STYLE_LABELS[k])
    t2.select_slider("Размер текста", options=list(textart.SIZE_SCALES), key="g_size")
    if not textart.EMOJI_AVAILABLE:
        st.caption("ℹ️ Эмодзи выводятся только при установленном шрифте fonts-noto-color-emoji; иначе они пропускаются.")


def _build_options() -> BatchOptions:
    return BatchOptions(
        query=st.session_state["g_query"],
        count=int(st.session_state["g_count"]),
        duration=int(st.session_state["g_duration"]),
        scenes=int(st.session_state["g_scenes"]),
        transition=st.session_state["g_transition"],
        framing=st.session_state["g_framing"],
        zoom=bool(st.session_state["g_zoom"]),
        soft_edges=bool(st.session_state["g_soft"]),
        music_choice=st.session_state["g_music"],
        music_volume=st.session_state["g_music_vol"] / 100,
        orig_volume=st.session_state["g_orig_vol"] / 100,
        top_text=st.session_state["g_top"],
        bottom_text=st.session_state["g_bottom"],
        text_style=st.session_state["g_style"],
        text_size=st.session_state["g_size"],
    )


def _run_batch() -> None:
    try:
        opts = _build_options()
    except (KeyError, TypeError, ValueError) as exc:
        st.error(f"Проверьте параметры: {exc}")
        return
    bar = st.progress(0.0, text="Подготовка…")
    logs: list[str] = []

    def progress(fraction: float, text: str) -> None:
        bar.progress(min(1.0, max(0.0, fraction)), text=text)

    try:
        result = generate_batch(opts, progress=progress, log_fn=logs.append)
    except GenerationError as exc:
        bar.empty()
        st.error(str(exc))
        st.session_state["g_logs"] = logs
        return
    except Exception as exc:  # noqa: BLE001 - keep the app alive, show the cause
        log.exception("Batch generation failed")
        bar.empty()
        st.error(f"Непредвиденная ошибка: {exc}")
        st.session_state["g_logs"] = logs
        return
    bar.progress(1.0, text="Готово ✅")
    st.session_state["g_results"] = [
        {"name": item.path.name, "title": item.source_title, "url": item.source_url,
         "index": item.index, "duration": item.duration, "music": item.music_name}
        for item in result.items
    ]
    st.session_state["g_notes"] = result.notes
    st.session_state["g_logs"] = logs
    st.toast(f"Готово: {len(result.items)} роликов", icon="🎬")


def _render_results() -> None:
    results = [r for r in st.session_state["g_results"] if (config.OUTPUT_DIR / r["name"]).is_file()]
    st.session_state["g_results"] = results
    for note in st.session_state["g_notes"]:
        st.warning(note)
    if not results:
        return
    st.markdown(f"#### 🎞️ Готовые ролики · {len(results)}")
    cols_per_row = 3
    for start in range(0, len(results), cols_per_row):
        row = results[start:start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, item in zip(cols, row):
            path = config.OUTPUT_DIR / item["name"]
            with col.container(border=True):
                st.markdown(
                    f"**Ролик {item['index']}** "
                    f"<span class='badge'>1080×1920</span><span class='badge'>{item['duration']:.0f} с</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Источник: {item['title'][:90]}")
                st.video(str(path))
                st.download_button("⬇️ Скачать MP4", data=path.read_bytes(), file_name=path.name,
                                   mime="video/mp4", key=f"dl_{item['name']}", width="stretch",
                                   type="primary")
                st.button("✂️ Открыть в редакторе", key=f"ed_{item['name']}", width="stretch",
                          on_click=open_in_editor, args=(item["name"],))
    logs = st.session_state.get("g_logs") or []
    if logs:
        with st.expander("🧾 Журнал генерации"):
            st.code("\n".join(logs), language=None)


def render() -> None:
    _init_defaults()
    st.markdown("### 🎬 Авто-генератор (Пакетная нарезка)")
    st.caption("Ищет ролики на YouTube, скачивает, нарезает в вертикальный формат и накладывает текст и музыку.")
    _render_presets()
    _render_controls()

    st.divider()
    run = st.button("🚀 Сгенерировать ролики", type="primary", width="stretch")
    if run:
        _run_batch()
    _render_results()
