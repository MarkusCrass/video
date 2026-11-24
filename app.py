"""Reels & Shorts Studio — Streamlit entry point.

Run locally:  streamlit run app.py
On a VPS:     see reels_studio.service and README.md
"""

from __future__ import annotations

import logging

import streamlit as st

from studio import config, security, storage
from studio.theme import hero, inject
from studio.ui import editor, generator, library, sidebar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(
    page_title="Reels & Shorts Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()
config.ensure_dirs()


def render_login() -> None:
    st.markdown(
        """<div class="login-wrap"><div class="login-card">
        <div class="moon">🌙</div><h2>Reels & Shorts Studio</h2>
        <p>Введите пароль, чтобы открыть студию</p></div></div>""",
        unsafe_allow_html=True,
    )
    _, middle, _ = st.columns([1, 1.3, 1])
    with middle:
        remaining = security.lock_remaining(st.session_state)
        if remaining:
            st.error(f"Слишком много неверных попыток. Подождите {remaining} с.")
        with st.form("login_form", clear_on_submit=False, border=False):
            password = st.text_input("Пароль", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Войти", type="primary", width="stretch",
                                              disabled=remaining > 0)
        if submitted:
            if security.check_password(password):
                st.session_state["auth_ok"] = True
                st.session_state.pop("fails", None)
                st.session_state.pop("lock_until", None)
                st.rerun()
            else:
                security.register_failure(st.session_state)
                st.error("Неверный пароль")


if not st.session_state.get("auth_ok"):
    render_login()
    st.stop()

storage.cleanup_old_temp()  # remove temp sources older than 24 h
sidebar.render()
hero("Reels & Shorts Studio", "Автопоиск, нарезка, озвучка и монтаж вертикальных видео 1080×1920 "
     "для Reels, Shorts, TikTok и VK Клипов")

tab_gen, tab_edit, tab_lib = st.tabs([
    "🎬 Авто-генератор (Пакетная нарезка)",
    "✂️ Студия монтажа и озвучки (Редактор видео)",
    "🎵 Библиотека треков (Suno / Музыка)",
])
with tab_gen:
    generator.render()
with tab_edit:
    editor.render()
with tab_lib:
    library.render()
