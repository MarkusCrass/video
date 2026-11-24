"""Dark Studio theme: CSS injected once per page (mobile-friendly sizes)."""

import streamlit as st

CSS = """
<style>
:root { --bg:#0E1117; --card:#161B22; --line:#2A313C; --accent:#8B5CF6; --gold:#FFD166; }
.stApp { background: var(--bg); }
header[data-testid="stHeader"] { background: rgba(14,17,23,.85); }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -.01em; }
.studio-hero { display:flex; align-items:center; gap:.9rem; margin:.2rem 0 1.1rem; }
.studio-hero .logo { font-size:2.1rem; line-height:1; }
.studio-hero h1 { font-size: clamp(1.3rem, 3.4vw, 2.1rem); margin:0; }
.studio-hero p { margin:.15rem 0 0; color:#8B949E; font-size:.95rem; }
.studio-card {
  background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 1.1rem 1.2rem; margin-bottom: .9rem;
}
.studio-card h4 { margin:.1rem 0 .35rem; font-size:1.02rem; }
.studio-card small, .studio-muted { color:#8B949E; }
.preset-hint { color:#8B949E; font-size:.86rem; margin:.25rem 0 .6rem; }
.badge { display:inline-block; padding:.12rem .55rem; border-radius:999px; font-size:.75rem;
  background: rgba(139,92,246,.18); color:#C4B5FD; border:1px solid rgba(139,92,246,.45); margin-right:.3rem; }
.login-wrap { max-width: 420px; margin: 9vh auto 0; }
.login-card { background: var(--card); border:1px solid var(--line); border-radius: 20px;
  padding: 2rem 1.6rem 1.6rem; box-shadow: 0 20px 60px rgba(0,0,0,.45); text-align:center; }
.login-card .moon { font-size: 3.2rem; line-height:1; margin-bottom:.35rem; }
.login-card h2 { margin:.2rem 0 .3rem; font-size:1.4rem; }
.login-card p { color:#8B949E; margin:0 0 1rem; }
div[data-testid="stTabs"] button[role="tab"] { font-size: 1rem; padding: .55rem .9rem; }
.stButton > button, .stDownloadButton > button {
  border-radius: 12px; min-height: 2.75rem; font-weight: 600; border:1px solid var(--line);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(135deg, #8B5CF6, #6D28D9); border: none; color: #fff;
}
.stButton > button:hover { border-color: var(--accent); }
div[data-testid="stVideo"] video { border-radius: 14px; }
div[data-testid="stAudioInput"] { border-radius: 14px; }
@media (max-width: 640px) {
  .block-container { padding-left: .8rem; padding-right: .8rem; }
  .stButton > button, .stDownloadButton > button { min-height: 3rem; font-size: 1.02rem; }
  .login-card { padding: 1.4rem 1.1rem; }
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""<div class="studio-hero"><div class="logo">🎬</div>
        <div><h1>{title}</h1><p>{subtitle}</p></div></div>""",
        unsafe_allow_html=True,
    )
