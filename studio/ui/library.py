"""Tab 3: music library (upload MP3/WAV, preview, delete)."""

from __future__ import annotations

import streamlit as st

from studio import music
from studio.ui.common import duration_of


def _delete(name: str) -> None:
    if music.delete_track(name):
        st.session_state["lib_flash"] = f"Трек «{name}» удалён"


def render() -> None:
    st.markdown("#### 📤 Загрузка треков")
    st.caption("Загружайте свои MP3/WAV (например, из Suno). Файлы сохраняются в папку `music/` на сервере.")
    uploads = st.file_uploader(
        "Перетащите файлы или выберите на телефоне/ПК",
        type=["mp3", "wav"],
        accept_multiple_files=True,
        key="lib_upload",
    )
    saved = st.session_state.setdefault("lib_saved", set())
    new_names: list[str] = []
    for item in uploads or []:
        signature = (item.name, item.size)
        if signature in saved:
            continue
        music.save_track(item.name, item.getvalue())
        saved.add(signature)
        new_names.append(item.name)
    if new_names:
        st.toast(f"Добавлено треков: {len(new_names)}", icon="🎵")

    if flash := st.session_state.pop("lib_flash", None):
        st.success(flash)

    st.markdown("#### 🎵 Библиотека")
    tracks = music.list_tracks()
    if not tracks:
        st.info("Библиотека пуста. Загрузите хотя бы один трек — он будет использоваться в генераторе и редакторе.")
        return
    st.caption(f"Треков: {len(tracks)}")
    for track in tracks:
        with st.container(border=True):
            left, right = st.columns([5, 1], vertical_alignment="center")
            seconds = duration_of(track)
            left.markdown(f"**{track.name}**  \n<span class='studio-muted'>{seconds:.0f} сек</span>",
                          unsafe_allow_html=True)
            right.button("🗑️", key=f"del_{track.name}", help="Удалить трек",
                         on_click=_delete, args=(track.name,), width="stretch")
            st.audio(str(track))
