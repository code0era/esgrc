"""
ESGRC Intelligence Platform — Streamlit Application
Sky Blue + White | Vertical Main Sections + Right-Side Chat Panel
"""

import io
import json
import time
from datetime import datetime

import anthropic
import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st

from utils.db import (
    append_chat_message,
    delete_report,
    get_report,
    get_user_reports,
    login_user,
    register_user,
    save_report,
)
from utils.esgrc_engine import generate_report
from utils.pdf_report import generate_pdf

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ESGRC Intelligence Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

/* ── Hide default Streamlit top bar decoration ───────────────────────── */
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"]    { display: none !important; }

/* ── Push content below our custom header ───────────────────────────── */
.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
html, body {
    overflow-x: hidden !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0284C7 0%, #0369A1 100%) !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.15) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.3) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.28) !important;
}

/* ── Section headers ─────────────────────────────────────────────────── */
.sec-header {
    display: flex; align-items: center; gap: 10px;
    border-bottom: 2px solid #BAE6FD;
    padding-bottom: 0.6rem; margin-bottom: 1.1rem;
    margin-top: 0.5rem;
}
.sec-header-text {
    font-size: 0.82rem; font-weight: 700; color: #0369A1;
    letter-spacing: 0.08em; text-transform: uppercase;
}

/* ── Score hero ──────────────────────────────────────────────────────── */
.score-hero {
    background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%);
    border-radius: 14px; padding: 1.4rem 1.8rem; color: white;
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(14,165,233,0.3);
}
.score-number { font-size: 2.8rem; font-weight: 800; letter-spacing: -2px; line-height: 1; }

/* ── File badge ──────────────────────────────────────────────────────── */
.file-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #DCFCE7; border: 1px solid #86EFAC; border-radius: 20px;
    padding: 3px 12px; font-size: 0.78rem; color: #166534; font-weight: 500; margin-top: 5px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    padding: 0.55rem 1.2rem !important; transition: all 0.2s !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #38BDF8 0%, #0EA5E9 100%) !important;
    box-shadow: 0 4px 16px rgba(14,165,233,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #CBD5E1 !important; transform: none !important; box-shadow: none !important;
}

/* ── Toggle chat button ──────────────────────────────────────────────── */
.toggle-btn > button {
    background: white !important; color: #0369A1 !important;
    border: 2px solid #7DD3FC !important; border-radius: 20px !important;
    padding: 0.35rem 1rem !important; font-size: 0.82rem !important;
}
.toggle-btn > button:hover {
    background: #E0F2FE !important; border-color: #0EA5E9 !important;
    transform: none !important; box-shadow: none !important;
}

/* ── Download button ─────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {
    background: #FFFFFF !important; color: #0369A1 !important;
    border: 2px solid #0EA5E9 !important;
    box-shadow: none !important; transform: none !important;
}

/* ── File uploader ───────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #F0F9FF !important; border-radius: 12px !important;
    border: 2px dashed #7DD3FC !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important; border: 1px solid #BAE6FD !important;
    overflow: hidden !important;
}

/* ── Metrics ─────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF; border: 1px solid #BAE6FD;
    border-radius: 12px; padding: 0.7rem 1rem;
}
[data-testid="stMetricValue"] { color: #0369A1 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #64748B !important; font-size: 0.75rem !important; }

/* ── Progress bar ────────────────────────────────────────────────────── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #0EA5E9, #38BDF8) !important;
    border-radius: 4px !important;
}

/* ── Text inputs ─────────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border: 1.5px solid #BAE6FD !important; border-radius: 10px !important;
    background: #FFFFFF !important; color: #0C4A6E !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #0EA5E9 !important;
    box-shadow: 0 0 0 3px rgba(14,165,233,0.15) !important;
}

/* ── Custom page header bar ──────────────────────────────────────────── */
.esgrc-header {
    background: linear-gradient(135deg, #0284C7 0%, #0369A1 60%, #0C4A6E 100%);
    border-radius: 0 !important;
    padding: 1.2rem 2.5rem;
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 2rem;
    box-shadow: 0 4px 20px rgba(2,132,199,0.25);
    border-bottom: 1px solid rgba(255,255,255,0.15);
    width: 100vw;
    position: relative;
    left: 50%;
    right: 50%;
    margin-left: -50vw;
    margin-right: -50vw;
}
.esgrc-header-left  { display:flex; align-items:center; gap:14px; }
.esgrc-header-logo  { font-size:1.8rem; line-height:1; }
.esgrc-header-title { font-size:1.2rem; font-weight:800; color:#FFFFFF; letter-spacing:-0.3px; }
.esgrc-header-sub   { font-size:0.72rem; color:rgba(255,255,255,0.72); margin-top:2px; letter-spacing:0.03em; }
.esgrc-header-right { display:flex; align-items:center; gap:16px; }
.esgrc-header-badge {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.75rem;
    color: white;
    font-weight: 500;
    display: flex; align-items: center; gap: 6px;
}
.esgrc-header-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #4ADE80;
    box-shadow: 0 0 6px #4ADE80;
    display: inline-block;
    animation: pulse-dot 2s infinite;
}
@keyframes pulse-dot {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:0.6; transform:scale(0.85); }
}
.esgrc-header-date  { font-size:0.72rem; color:rgba(255,255,255,0.65); }

/* ── Page footer ─────────────────────────────────────────────────────── */
.esgrc-footer {
    background: linear-gradient(135deg, #0C4A6E 0%, #0369A1 100%);
    border-radius: 0 !important;
    padding: 1.5rem 2.5rem;
    margin-top: 3.5rem;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 0.5rem;
    width: 100vw;
    position: relative;
    left: 50%;
    right: 50%;
    margin-left: -50vw;
    margin-right: -50vw;
}
.esgrc-footer-brand { font-size:0.85rem; font-weight:700; color:#FFFFFF; letter-spacing:-0.2px; }
.esgrc-footer-links { display:flex; gap:20px; }
.esgrc-footer-link  { font-size:0.72rem; color:rgba(255,255,255,0.65); text-decoration:none; }
.esgrc-footer-copy  { font-size:0.7rem; color:rgba(255,255,255,0.5); }
.esgrc-footer-security {
    display:flex; align-items:center; gap:6px;
    font-size:0.7rem; color:rgba(255,255,255,0.65);
    background: rgba(255,255,255,0.08);
    border-radius: 12px; padding: 3px 10px;
}

/* ── Chat right panel ────────────────────────────────────────────────── */
.chat-panel-wrap {
    background: #FFFFFF;
    border: 1.5px solid #BAE6FD;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(14,165,233,0.12);
    display: flex;
    flex-direction: column;
    min-height: 600px;
    position: sticky;
    top: 10px;
}
.chat-panel-header {
    background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%);
    padding: 0.8rem 1.1rem;
    color: white; font-weight: 700; font-size: 0.9rem;
    display: flex; align-items: center; justify-content: space-between;
    flex-shrink: 0;
}
.chat-panel-score {
    background: #F0F9FF; border-bottom: 1px solid #BAE6FD;
    padding: 0.55rem 1rem;
    font-size: 0.78rem; color: #0369A1;
    flex-shrink: 0;
}
.chat-panel-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 0.6rem 0.7rem 0.4rem;
}

/* ── Streamlit chat messages ─────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0.15rem 0 !important;
}
[data-testid="stChatMessageContent"] {
    background: #FFFFFF !important;
    border: 1px solid #BAE6FD !important;
    border-radius: 12px !important;
    padding: 0.6rem 0.85rem !important;
    font-size: 0.83rem !important;
    color: #0C4A6E !important;
    line-height: 1.55 !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
hr { border: none !important; border-top: 1.5px solid #E0F2FE !important; margin: 1.1rem 0 !important; }

/* ── Tabs ────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button { font-weight: 600 !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #0369A1 !important; }

/* ── Scrollbar ───────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #F0F9FF; }
::-webkit-scrollbar-thumb { background: #7DD3FC; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
def init_session():
    defaults = {
        "logged_in":        False,
        "user_id":          None,
        "username":         None,
        "csv_bytes":        None,
        "json_data":        None,
        "csv_filename":     "",
        "json_filename":    "",
        "report_id":        None,
        "report_content":   "",
        "report_context":   None,
        "report_generated": False,
        "is_generating":    False,
        "chat_messages":    [],
        "chat_open":        True,   # right panel visibility
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def score_color(v):
    return "#10B981" if v >= 85 else ("#F59E0B" if v >= 75 else "#EF4444")

def score_label(v):
    return "🟢 Good" if v >= 85 else ("🟡 Moderate" if v >= 75 else "🔴 Needs Attention")

def build_system_prompt(ctx: Optional[dict]) -> str:
    if not ctx:
        return """You are an expert ESGRC (Environmental, Social, Governance, Risk, and Compliance) Advisor.
You help users understand ESG frameworks, risk compliance management, audit preparedness, and industry standards.
Encourage them to upload their metrics CSV and config JSON files in the panel on the left to generate their interactive performance report.

IMPORTANT FORMATTING RULES:
- Do NOT use # headings or markdown symbols like ** or * in your response.
- Write in plain, clear, professional prose.
- Use plain numbered lists (1. 2. 3.) or simple bullet points with a dash (-) only.
- Keep responses concise and actionable.
- Be direct, professional, and helpful.
"""
    low_m  = "\n".join(f"  • {m['name']} ({m['id']}): {m['score']}" for m in ctx.get("low_metrics", []))
    low_g  = "\n".join(f"  • {g['name']} ({g['id']}): {g['score']}" for g in ctx.get("low_groups", []))
    low_sm = "\n".join(f"  • {s['name']} ({s['id']}): {s['score']}" for s in ctx.get("low_sub_modules", []))
    return f"""You are an expert ESGRC analyst embedded in a professional reporting platform.

Module: {ctx.get("module_name")} ({ctx.get("module_id")})
Overall Score: {ctx.get("overall_score")} / 100  ({score_label(ctx.get("overall_score", 0))})
Metrics: {ctx.get("total_metrics")}  |  Groups: {ctx.get("total_groups")}  |  Sub-Modules: {ctx.get("total_sub_modules")}

Low-Performing Metrics:
{low_m}

Low-Performing Groups:
{low_g}

Low-Performing Sub-Modules:
{low_sm}

Full Report:
{ctx.get("report_text", "")}

IMPORTANT FORMATTING RULES:
- Do NOT use # headings or markdown symbols like ** or * in your response.
- Write in plain, clear, professional prose.
- Use plain numbered lists (1. 2. 3.) or simple bullet points with a dash (-) only.
- Keep responses concise and actionable.
- Be direct, professional, and helpful.
"""

def stream_claude(messages: list, system: str):
    """Generator that yields text tokens from Claude streaming API."""
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    with client.messages.stream(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=system,
        messages=messages,
    ) as stream:
        for token in stream.text_stream:
            yield token


# ─────────────────────────────────────────────────────────────────────────────
# AUTH SCREEN
# ─────────────────────────────────────────────────────────────────────────────
def render_auth():
    _, col_m, _ = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown("""
<div style="text-align:center; padding:2.5rem 0 2rem;">
    <div style="font-size:2.8rem; margin-bottom:0.6rem;">🛡️</div>
    <div style="font-size:1.75rem; font-weight:800; color:#0C4A6E;">ESGRC Intelligence</div>
    <div style="font-size:0.85rem; color:#64748B; margin-top:4px;">
        Enterprise ESG · Risk · Compliance Platform
    </div>
</div>
""", unsafe_allow_html=True)

        tab_in, tab_reg = st.tabs(["🔑  Sign In", "✨  Create Account"])

        with tab_in:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Password")
                sub = st.form_submit_button("Sign In →", use_container_width=True)
            if sub:
                if not username or not password:
                    st.error("Please fill in all fields.")
                else:
                    res = login_user(username, password)
                    if res["ok"]:
                        st.session_state.logged_in = True
                        st.session_state.user_id   = str(res["user"]["_id"])
                        st.session_state.username  = res["user"]["username"]
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error(res["error"])

        with tab_reg:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("reg_form"):
                ru = st.text_input("Username",         placeholder="Choose a username",   key="ru")
                re_ = st.text_input("Email",           placeholder="you@company.com",     key="re")
                rp = st.text_input("Password",         type="password", placeholder="Min 6 chars", key="rp")
                rp2= st.text_input("Confirm password", type="password", placeholder="Repeat",      key="rp2")
                sub2 = st.form_submit_button("Create Account →", use_container_width=True)
            if sub2:
                if not all([ru, re_, rp, rp2]): st.error("Fill in all fields.")
                elif rp != rp2: st.error("Passwords do not match.")
                elif len(rp) < 6: st.error("Password must be 6+ characters.")
                else:
                    res = register_user(ru, re_, rp)
                    st.success("Account created! Please sign in.") if res["ok"] else st.error(res["error"])


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(f"""
<div style="padding:0.8rem 0 0.5rem;">
    <div style="font-size:0.68rem; opacity:0.75; text-transform:uppercase; letter-spacing:0.1em;">Signed in as</div>
    <div style="font-size:1rem; font-weight:700; margin-top:3px;">👤 {st.session_state.username}</div>
</div>""", unsafe_allow_html=True)

        if st.button("Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

        st.markdown("---")
        st.markdown('<div style="font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; opacity:0.7; margin-bottom:0.6rem;">📁 Report History</div>', unsafe_allow_html=True)

        reports = get_user_reports(st.session_state.user_id)
        if not reports:
            st.markdown('<p style="opacity:0.6; font-size:0.82rem; text-align:center; padding:1rem 0;">No reports yet</p>', unsafe_allow_html=True)
        else:
            for rep in reports:
                rid    = str(rep["_id"])
                fn     = rep.get("csv_filename", "report")[:22]
                score  = rep.get("overall_score", 0.0)
                created= rep.get("created_at", datetime.now())
                ds     = created.strftime("%b %d, %H:%M") if isinstance(created, datetime) else "—"
                active = st.session_state.report_id == rid
                bg = "rgba(255,255,255,0.22)" if active else "rgba(255,255,255,0.1)"
                sc = "🟢" if score >= 85 else ("🟡" if score >= 75 else "🔴")

                st.markdown(f"""
<div style="background:{bg}; border:1px solid rgba(255,255,255,0.2); border-radius:10px;
     padding:0.55rem 0.75rem; margin-bottom:0.4rem;">
  <div style="font-size:0.8rem; font-weight:600;">{fn}</div>
  <div style="font-size:0.7rem; opacity:0.72; margin-top:2px;">{ds}</div>
  <div style="font-size:0.75rem; margin-top:3px;">{sc} <b>{score:.1f}</b></div>
</div>""", unsafe_allow_html=True)

                bc, dc = st.columns([3, 1])
                with bc:
                    if st.button("Load", key=f"ld_{rid}", use_container_width=True):
                        full = get_report(rid)
                        if full:
                            st.session_state.report_id       = rid
                            st.session_state.report_content  = full.get("report_content", "")
                            st.session_state.report_context  = full.get("context_data", {})
                            st.session_state.report_generated= True
                            st.session_state.chat_messages   = [
                                {"role": m["role"], "content": m["content"]}
                                for m in full.get("chat_history", [])
                            ]
                            st.rerun()
                with dc:
                    if st.button("🗑", key=f"dl_{rid}", help="Delete"):
                        if delete_report(rid, st.session_state.user_id):
                            if st.session_state.report_id == rid:
                                st.session_state.report_id       = None
                                st.session_state.report_content  = ""
                                st.session_state.report_generated= False
                                st.session_state.chat_messages   = []
                                st.session_state.report_context  = None
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# HEADER  — branded bar + chat toggle
# ─────────────────────────────────────────────────────────────────────────────
def render_header():
    now_str = datetime.now().strftime("%d %b %Y  ·  %H:%M")
    user    = st.session_state.get("username", "")

    # Left side of header HTML
    toggle_html = ""
    st.markdown(f"""
<div class="esgrc-header">
    <div class="esgrc-header-left">
        <div class="esgrc-header-logo">🛡️</div>
        <div>
            <div class="esgrc-header-title">ESGRC Intelligence Platform</div>
            <div class="esgrc-header-sub">Enterprise ESG &nbsp;·&nbsp; Risk &nbsp;·&nbsp; Compliance — Performance Analysis &amp; AI Reporting</div>
        </div>
    </div>
    <div class="esgrc-header-right">
        <div class="esgrc-header-badge">
            <span class="esgrc-header-dot"></span> Live
        </div>
        <div class="esgrc-header-badge">👤 {user}</div>
        <div class="esgrc-header-date">📅 {now_str}</div>
    </div>
</div>
""", unsafe_allow_html=True)

    # Chat toggle button (rendered below the header bar, right-aligned)
    _, col_btn = st.columns([5, 1])
    with col_btn:
        label = "◀ Hide Chat" if st.session_state.chat_open else "Show Chat ▶"
        st.markdown('<div class="toggle-btn">', unsafe_allow_html=True)
        if st.button(label, key="chat_toggle", use_container_width=True):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
def render_footer():
    st.markdown("""
<div class="esgrc-footer">
    <div>
        <div class="esgrc-footer-brand">🛡️ ESGRC Intelligence Platform</div>
        <div class="esgrc-footer-copy">© 2024 ESGRC Intelligence · All rights reserved · v2.0</div>
    </div>
    <div class="esgrc-footer-security">
        🔒 End-to-end secure &nbsp;·&nbsp; Data stored in your MongoDB instance
    </div>
    <div class="esgrc-footer-links">
        <span class="esgrc-footer-link">Enterprise ESG</span>
        <span class="esgrc-footer-link">Risk Management</span>
        <span class="esgrc-footer-link">Compliance</span>
        <span class="esgrc-footer-link">AI Analytics</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SECTIONS  (rendered in left/center area)
# ─────────────────────────────────────────────────────────────────────────────

def render_upload_section():
    st.markdown('<div class="sec-header"><span>📂</span><span class="sec-header-text">Step 1 — Upload Data Files</span></div>', unsafe_allow_html=True)
    col_csv, col_json = st.columns(2, gap="large")

    with col_csv:
        st.markdown("**📄 Metric CSV File**")
        st.caption("e.g. `input_metric_values_esgrc.csv`")
        csv_f = st.file_uploader("CSV", type=["csv"], key="csv_up", label_visibility="collapsed")
        if csv_f:
            st.session_state.csv_bytes    = csv_f.read()
            st.session_state.csv_filename = csv_f.name
        if st.session_state.csv_bytes:
            st.markdown(f'<div class="file-badge">✅ {st.session_state.csv_filename}</div>', unsafe_allow_html=True)

    with col_json:
        st.markdown("**🔧 Config JSON File**")
        st.caption("e.g. `esgrc_performance_json_file.json`")
        json_f = st.file_uploader("JSON", type=["json"], key="json_up", label_visibility="collapsed")
        if json_f:
            try:
                st.session_state.json_data     = json.loads(json_f.read())
                st.session_state.json_filename = json_f.name
            except json.JSONDecodeError:
                st.error("Invalid JSON — please check the file format.")
        if st.session_state.json_data:
            st.markdown(f'<div class="file-badge">✅ {st.session_state.json_filename}</div>', unsafe_allow_html=True)


def render_summary_and_generate():
    jd = st.session_state.json_data
    subs = len(jd.get("sub_modules", []))
    grps = sum(len(sm.get("groups", [])) for sm in jd.get("sub_modules", []))
    mets = sum(len(g.get("value", [])) for sm in jd.get("sub_modules", []) for g in sm.get("groups", []))

    st.markdown('<div class="sec-header"><span>📊</span><span class="sec-header-text">Step 2 — Data Summary</span></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Module",      jd.get("module_id", "—"))
    c2.metric("Sub-Modules", subs)
    c3.metric("Groups",      grps)
    c4.metric("Metrics",     mets)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-header"><span>⚡</span><span class="sec-header-text">Step 3 — Generate Report</span></div>', unsafe_allow_html=True)

    col_btn, col_desc = st.columns([1, 3])
    with col_btn:
        if st.button("⚡  Generate Report", use_container_width=True):
            st.session_state.is_generating   = True
            st.session_state.report_generated= False
            st.session_state.report_content  = ""
            st.session_state.report_id       = None
            st.session_state.chat_messages   = []
            st.session_state.report_context  = None
            st.rerun()
    with col_desc:
        st.markdown('<div style="color:#64748B; font-size:0.82rem; padding-top:0.65rem;">Runs the full ESGRC weighted-average pipeline and identifies the lowest-performing metrics, groups, and sub-modules.</div>', unsafe_allow_html=True)


def render_generating():
    st.markdown('<div class="sec-header"><span>⚙️</span><span class="sec-header-text">Generating Report…</span></div>', unsafe_allow_html=True)
    prog   = st.progress(0, text="Initialising ESGRC engine…")
    status = st.empty()
    steps  = [
        (20, "Loading CSV and JSON data…"),
        (40, "Extracting metric, group and sub-module IDs…"),
        (60, "Calculating weighted averages…"),
        (80, "Identifying low-performing entities…"),
        (92, "Building report sections…"),
    ]
    for pct, msg in steps:
        prog.progress(pct, text=msg)
        status.info(f"⚙️ {msg}")
        time.sleep(0.25)

    try:
        _, full_report, context = generate_report(
            st.session_state.json_data,
            st.session_state.csv_bytes,
        )
        
        prog.progress(95, text="Generating AI summary…")
        status.info("⚙️ Generating AI summary…")
        
        try:
            client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
            system = build_system_prompt(context)
            resp = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": "Please provide a concise executive summary (2-3 paragraphs) of the report's findings, highlighting the most critical areas needing attention based on the low-performing metrics, groups, and sub-modules."}]
            )
            context["ai_summary"] = resp.content[0].text
        except Exception as e:
            context["ai_summary"] = f"Failed to generate AI summary: {e}"

        prog.progress(100, text="✅ Done!")
        status.success("✅ Report generated and saved.")
        time.sleep(0.4)
        prog.empty(); status.empty()

        st.session_state.report_content   = full_report
        st.session_state.report_context   = context
        st.session_state.report_generated = True
        st.session_state.is_generating    = False
        st.session_state.chat_open        = True

        rep_id = save_report(
            user_id        = st.session_state.user_id,
            csv_filename   = st.session_state.csv_filename,
            json_filename  = st.session_state.json_filename,
            report_content = full_report,
            context        = context,
        )
        st.session_state.report_id = rep_id
        st.rerun()

    except Exception as e:
        prog.empty()
        status.error(f"❌ Report generation failed: {e}")
        st.session_state.is_generating = False


def render_report():
    ctx   = st.session_state.report_context
    score = ctx.get("overall_score", 0.0)

    st.markdown('<div class="sec-header"><span>📋</span><span class="sec-header-text">Step 4 — Performance Report</span></div>', unsafe_allow_html=True)

    # Score hero
    st.markdown(f"""
<div class="score-hero">
    <div>
        <div style="font-size:0.72rem; opacity:0.82; text-transform:uppercase; letter-spacing:0.1em;">
            {ctx.get("module_name", ctx.get("module_id", "—"))}
        </div>
        <div style="font-size:1rem; font-weight:600; margin-top:5px;">Overall Module Performance</div>
        <div style="font-size:0.82rem; opacity:0.85; margin-top:8px;">
            {ctx.get("total_metrics")} Metrics &nbsp;·&nbsp;
            {ctx.get("total_groups")} Groups &nbsp;·&nbsp;
            {ctx.get("total_sub_modules")} Sub-Modules
        </div>
    </div>
    <div style="text-align:right;">
        <div class="score-number">{score:.1f}</div>
        <div style="font-size:0.75rem; opacity:0.82; margin-top:4px;">/ 100 &nbsp; {score_label(score)}</div>
    </div>
</div>
""", unsafe_allow_html=True)

    # Tables
    def make_table(data, cols):
        df = pd.DataFrame(data)
        if df.empty:
            st.info("No data available.")
            return
        df.index = range(1, len(df) + 1)
        df.columns = cols
        st.dataframe(
            df, use_container_width=True,
            column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.2f")},
        )

    st.markdown("#### 📊 Low-Performing Metrics")
    make_table(ctx.get("low_metrics", []), ["Metric ID", "Metric Name", "Score"])

    st.markdown("#### 📊 Low-Performing Groups")
    make_table(ctx.get("low_groups", []),  ["Group ID",  "Group Name",  "Score"])

    st.markdown("#### 📊 Low-Performing Sub-Modules")
    make_table(ctx.get("low_sub_modules", []), ["Sub-Module ID", "Sub-Module Name", "Score"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── PDF download ───────────────────────────────────────────────────────
    col_dl, col_info, _ = st.columns([1.2, 2, 1.5])
    with col_dl:
        try:
            pdf_bytes = generate_pdf(ctx)
            st.download_button(
                label="⬇️  Download PDF Report",
                data=pdf_bytes,
                file_name=f"ESGRC_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF generation error: {e}")
            # Fallback to txt
            st.download_button(
                label="⬇️  Download .txt (fallback)",
                data=st.session_state.report_content,
                file_name=f"esgrc_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
    with col_info:
        st.markdown(
            '<div style="color:#64748B; font-size:0.8rem; padding-top:0.6rem;">'
            '📄 Professional A4 PDF with score card, data tables, header & footer.</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CHAT PANEL  — flexible, scrollable, right-side
# ─────────────────────────────────────────────────────────────────────────────
def render_chat_panel():
    ctx = st.session_state.report_context
    messages      = st.session_state.chat_messages
    n_msgs        = len(messages)

    if not ctx:
        score = 0.0
        system_prompt = build_system_prompt(None)
        
        # ── Panel header ────────────────────────────────────────────────────────
        st.markdown(f"""
<div class="chat-panel-header">
    <span>🤖 AI Advisor — Claude</span>
    <span style="font-size:0.7rem; opacity:0.8; font-weight:400;">{n_msgs} message{'s' if n_msgs!=1 else ''}</span>
</div>
<div class="chat-panel-score">
    <b>General ESGRC Assistant</b> &nbsp;·&nbsp;
    <span style="color:#0EA5E9; font-weight:700;">Online</span>
</div>
""", unsafe_allow_html=True)
    else:
        score = ctx.get("overall_score", 0.0)
        system_prompt = build_system_prompt(ctx)
        
        # ── Panel header ────────────────────────────────────────────────────────
        st.markdown(f"""
<div class="chat-panel-header">
    <span>🤖 AI Analyst — Claude</span>
    <span style="font-size:0.7rem; opacity:0.8; font-weight:400;">{n_msgs} message{'s' if n_msgs!=1 else ''}</span>
</div>
<div class="chat-panel-score">
    <b>{ctx.get('module_name','')}</b> &nbsp;·&nbsp;
    <span style="color:{score_color(score)}; font-weight:700;">{score:.1f}</span>
    <span style="color:#64748B;"> / 100 &nbsp;{score_label(score)}</span>
</div>
""", unsafe_allow_html=True)

    # ── Suggestion chips (first visit only) ─────────────────────────────────
    if not messages:
        st.markdown('<div style="padding:0.5rem 0.2rem;">', unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.73rem; color:#64748B; font-weight:600; margin:0 0 6px;">💡 Quick questions to get started:</p>', unsafe_allow_html=True)
        if not ctx:
            suggestions = [
                "What is double materiality in ESG?",
                "How do I prepare for a CSRD audit?",
                "What are scope 1, 2, and 3 emissions?",
                "How can I improve compliance score?",
                "Explain risk mitigation vs transference",
                "What is a compliance threshold?",
            ]
        else:
            suggestions = [
                "Which area needs the most urgent action?",
                "Explain the overall module score",
                "What are the top 3 compliance risks?",
                "Recommend actions for the lowest metrics",
                "Compare sub-module performance",
                "Which groups are closest to threshold?",
            ]
        for i, sug in enumerate(suggestions):
            if st.button(sug, key=f"sug_{i}", use_container_width=True):
                messages.append({"role": "user", "content": sug})
                if st.session_state.report_id:
                    append_chat_message(st.session_state.report_id, "user", sug)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Scrollable chat history (flexible height, always grows) ─────────────
    # Compute dynamic height: taller when more messages, capped at 540px
    dyn_h = min(200 + n_msgs * 60, 540)
    chat_box = st.container(height=dyn_h)
    with chat_box:
        if not messages:
            st.markdown(
                '<div style="text-align:center; color:#94A3B8; font-size:0.8rem; padding:2rem 0;">'
                '✨ Start a conversation above</div>',
                unsafe_allow_html=True,
            )
        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # ── Chat input at bottom ─────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_input(
            "Message",
            placeholder="Ask about risks, actions, scores…",
            label_visibility="collapsed",
            key="chat_inp",
        )
        send = st.form_submit_button("Send →", use_container_width=True)

    if send and user_input.strip():
        q = user_input.strip()
        messages.append({"role": "user", "content": q})
        if st.session_state.report_id:
            append_chat_message(st.session_state.report_id, "user", q)

        claude_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]

        with st.chat_message("assistant"):
            full_response = st.write_stream(stream_claude(claude_msgs, system_prompt))

        messages.append({"role": "assistant", "content": full_response})
        st.session_state.chat_messages = messages
        if st.session_state.report_id:
            append_chat_message(st.session_state.report_id, "assistant", full_response)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if not st.session_state.logged_in:
        render_auth()
        return

    render_sidebar()
    render_header()

    import utils.db as db
    if db.should_use_sqlite():
        st.warning("⚠️ **Running in Local Offline Mode (SQLite)** because the MongoDB cluster is unreachable. Your data is being stored locally in `esgrc_local.db`.")

    st.divider()

    # ── Split layout into left column (workflow/report) and right column (agent chat) ──
    if st.session_state.get("chat_open", True):
        col_left, col_right = st.columns([2.6, 1.4], gap="large")
    else:
        col_left = st.container()
        col_right = None

    with col_left:
        # ── Step 1: Upload (always visible) ───────────────────────────────────
        render_upload_section()

        # Evaluate AFTER render_upload_section() has set session state
        has_csv  = st.session_state.csv_bytes is not None
        has_json = st.session_state.json_data is not None

        # ── Step 2 + 3: Summary & Generate (only when both files ready) ───────
        if has_csv and has_json:
            st.divider()
            render_summary_and_generate()

        # ── Generating progress ───────────────────────────────────────────────
        if st.session_state.is_generating:
            st.divider()
            render_generating()

        # ── Report ────────────────────────────────────────────────────────────
        show_report = (
            st.session_state.report_generated
            and st.session_state.report_context is not None
        )

        if show_report and not st.session_state.is_generating:
            st.divider()
            render_report()

        elif not show_report and not st.session_state.is_generating and (not has_csv or not has_json):
            # Onboarding hint
            st.markdown("<br>", unsafe_allow_html=True)
            st.info(
                "👆 **Get started:** Upload your **Metric CSV** and **Config JSON** files "
                "above, then click **⚡ Generate Report**.",
                icon="ℹ️",
            )

    if col_right:
        with col_right:
            render_chat_panel()

    # ── Page footer ────────────────────────────────────────────────────────
    render_footer()


if __name__ == "__main__":
    main()
