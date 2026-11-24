"""Sidebar: disk space, temp cleanup, library counters, logout."""

from __future__ import annotations

import streamlit as st

from studio import config, music, storage
from studio.ui.common import fmt_bytes


def _clear_temp() -> None:
    removed = storage.clear_temp()
    st.session_state["tmp_flash"] = f"Удалено временных файлов: {removed}"


def _logout() -> None:
    for key in ("auth_ok",):
        st.session_state.pop(key, None)


def render() -> None:
    with st.sidebar:
        st.markdown("### 🎬 Reels & Shorts Studio")
        st.caption("Студия вертикальных видео 1080×1920")

        st.markdown("#### 💾 Место на диске")
        disk = storage.disk_info()
        st.progress(min(1.0, disk.used_fraction), text=f"Свободно {fmt_bytes(disk.free)} из {fmt_bytes(disk.total)}")
        st.caption(f"Временные файлы: {fmt_bytes(storage.temp_size())} · старше 24 ч удаляются автоматически")
        st.button("🧹 Очистить временные файлы", on_click=_clear_temp, width="stretch")
        if flash := st.session_state.pop("tmp_flash", None):
            st.success(flash)

        st.markdown("#### 📦 Статистика")
        st.caption(
            f"Готовых роликов: {len(storage.list_outputs())} · "
            f"треков в библиотеке: {len(music.list_tracks())}"
        )
        st.caption(f"ffmpeg: {config.ffmpeg_source()} · порт {config.PORT}")

        st.divider()
        st.button("🔒 Выйти", on_click=_logout, width="stretch")
