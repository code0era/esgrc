"""
RISK INTELL Platform — Streamlit Application (Cache Cleared)
Sky Blue + White | Vertical Main Sections + Right-Side Chat Panel
"""

import io
import json
import os
import tempfile
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from groq import Groq
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
from utils.pipeline_engine import PIPELINE_STEPS

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RISK INTELL Platform",
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

/* ── Hide default Streamlit top bar decoration & footer ───────────────── */
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"]    { display: none !important; }
header[data-testid="stHeader"] { 
    background: transparent !important; 
    z-index: 120 !important;
    pointer-events: none !important; /* Allow clicking through transparent parts */
}
footer, [data-testid="stFooter"] { display: none !important; }

/* ── Highlight Sidebar Toggle Button ──────────────────────────────────── */
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {
    background-color: #00C853 !important;
    border-radius: 8px !important;
    margin: 10px !important;
    color: #FFFFFF !important;
    border: 1px solid #00E676 !important;
    transition: all 0.3s ease !important;
    z-index: 120 !important;
    pointer-events: auto !important; /* Re-enable clicking for the button */
    position: fixed !important;
    top: 110px !important;
    left: 15px !important;
}
[data-testid="collapsedControl"]:hover, [data-testid="stSidebarCollapsedControl"]:hover {
    background-color: #00E676 !important;
}
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] svg {
    fill: #FFFFFF !important;
    stroke: #FFFFFF !important;
}

/* ── Reset margins and paddings for all layout wrappers ─────────────── */
[data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"], [data-testid="stMainBlockContainer"], .main, .block-container, [data-testid="stApp"] {
    padding-top: 0px !important;
    margin-top: 0px !important;
    padding-bottom: 80px !important; /* Space for the sticky footer */
    margin-bottom: 0px !important;
}
div[data-testid="element-container"]:has(style) {
    display: none !important;
}
iframe {
    margin-top: 0px !important;
}
html, body {
    overflow-x: hidden !important;
}

/* ── Increase Base Font Weight ───────────────────────────────────────── */
p, span, div, label {
    font-weight: 500 !important;
}
h1, h2, h3, h4, h5, h6 {
    font-weight: 800 !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #06363D 0%, #085558 100%) !important;
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
    border-bottom: 2px solid #84BABF;
    padding-bottom: 0.6rem; margin-bottom: 1.1rem;
    margin-top: 0.5rem;
}
.sec-header-text {
    font-size: 1.1rem; font-weight: 700; color: #0D6F73;
    letter-spacing: 0.08em; text-transform: uppercase;
}

/* ── Score hero ──────────────────────────────────────────────────────── */
.score-hero {
    background: linear-gradient(135deg, #085558 0%, #06363D 100%);
    border-radius: 14px; padding: 1.4rem 1.8rem; color: white;
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(6,54,61,0.3);
}
.score-number { font-size: 2.8rem; font-weight: 800; letter-spacing: -2px; line-height: 1; }

/* ── File badge ──────────────────────────────────────────────────────── */
.file-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #DCFCE7; border: 1px solid #86EFAC; border-radius: 20px;
    padding: 3px 12px; font-size: 1rem; color: #166534; font-weight: 500; margin-top: 5px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #0D6F73 0%, #085558 100%) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    padding: 0.55rem 1.2rem !important; transition: all 0.2s !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #84BABF 0%, #0D6F73 100%) !important;
    box-shadow: 0 4px 16px rgba(13,111,115,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #CBD5E1 !important; transform: none !important; box-shadow: none !important;
}

/* ── Toggle chat button ──────────────────────────────────────────────── */
.toggle-btn > button {
    background: white !important; color: #085558 !important;
    border: 2px solid #84BABF !important; border-radius: 20px !important;
    padding: 0.35rem 1rem !important; font-size: 1.1rem !important;
}
.toggle-btn > button:hover {
    background: #E0EDE9 !important; border-color: #0D6F73 !important;
    transform: none !important; box-shadow: none !important;
}

/* ── Download button ─────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {
    background: #FFFFFF !important; color: #0D6F73 !important;
    border: 2px solid #0D6F73 !important;
    box-shadow: none !important; transform: none !important;
}

/* ── File uploader ───────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #E0EDE9 !important; border-radius: 12px !important;
    border: 2px dashed #84BABF !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important; border: 1px solid #84BABF !important;
    overflow: hidden !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    color: #64748B !important;
    padding: 0.5rem 1.2rem !important;
    transition: all 0.2s ease !important;
}
button[data-baseweb="tab"]:hover {
    color: #0D6F73 !important;
    background-color: rgba(13,111,115,0.05) !important;
    border-radius: 6px !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    font-weight: 800 !important;
    color: #0D6F73 !important;
    background-color: rgba(13,111,115,0.1) !important;
    border-radius: 6px !important;
}

/* ── Metrics ─────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF; border: 1px solid #84BABF;
    border-radius: 12px; padding: 0.7rem 1rem;
}
[data-testid="stMetricValue"] { color: #0D6F73 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #085558 !important; font-size: 1rem !important; }

/* ── Progress bar ────────────────────────────────────────────────────── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #0D6F73, #84BABF) !important;
    border-radius: 4px !important;
}

/* ── Text inputs ─────────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border: 1.5px solid #84BABF !important; border-radius: 10px !important;
    background: #FFFFFF !important; color: #06363D !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #0D6F73 !important;
    box-shadow: 0 0 0 3px rgba(13,111,115,0.15) !important;
}

/* ── Hide 'Press Enter to submit form' hint ──────────────────────────── */
[data-testid="InputInstructions"] {
    display: none !important;
}

/* ── Prevent Streamlit from fading/whitening the screen during processing ─ */
div[data-testid="element-container"], div[data-testid="stVerticalBlock"] {
    opacity: 1 !important;
    transition: none !important;
}

/* ── Custom page header bar ──────────────────────────────────────────── */
div[data-testid="stHorizontalBlock"]:has(.risk-intell-header-left) {
    background: linear-gradient(135deg, #06363D 0%, #085558 100%) !important;
    padding: 0.5rem 3rem !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    z-index: 99999 !important;
    margin: 0 !important;
    border-bottom: 2px solid #0D6F73 !important;
    box-shadow: 0 8px 15px -5px rgba(0,0,0,0.5) !important;
    align-items: center !important;
}
[data-testid="stAppViewBlockContainer"] {
    padding-top: 90px !important;
}
.risk-intell-header-left  { display:flex; align-items:center; gap:14px; }
.risk-intell-header-logo  { font-size:1.8rem; line-height:1; }
.risk-intell-header-title { font-size:1.4rem; font-weight:800; color:#FFFFFF; letter-spacing:-0.3px; }
.risk-intell-header-sub   { font-size:0.85rem; color:#84BABF; margin-top:2px; letter-spacing:0.03em; font-weight: 500; }
.risk-intell-header-right { display:flex; align-items:center; gap:16px; }
.risk-intell-header-badge {
    background: #DCFCE7;
    border: 1px solid #86EFAC;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.75rem;
    color: #4ADE80;
    font-weight: 600;
    display: flex; align-items: center; gap: 6px;
    border: 1px solid rgba(74, 222, 128, 0.4);
    background: rgba(74, 222, 128, 0.1);
}
.risk-intell-header-dot {
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
.risk-intell-header-date  { font-size:0.75rem; font-weight: 500; color:#84BABF; }

/* ── Page footer ─────────────────────────────────────────────────────── */
.risk-intell-footer {
    background: linear-gradient(135deg, #085558 0%, #06363D 100%);
    border-radius: 0 !important;
    padding: 1rem 2.5rem;
    margin: 0 !important;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 0.5rem;
    width: 100vw !important;
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    z-index: 999999;
}
.risk-intell-footer-brand { font-size:1rem; font-weight:700; color:#FFFFFF; letter-spacing:-0.2px; }
.risk-intell-footer-links { display:flex; gap:20px; }
.risk-intell-footer-link  { font-size:0.9rem; color:rgba(255,255,255,0.65); text-decoration:none; }
.risk-intell-footer-copy  { font-size:0.85rem; color:rgba(255,255,255,0.5); }
.risk-intell-footer-security {
    display:flex; align-items:center; gap:6px;
    font-size:0.85rem; color:rgba(255,255,255,0.65);
    background: rgba(255,255,255,0.08);
    border-radius: 12px; padding: 4px 12px;
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

/* ── Pipeline step cards ─────────────────────────────────────────────── */
@keyframes pipe-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.6; }
}
.pipeline-running-row { animation: pipe-pulse 1.2s ease-in-out infinite; }

/* ── Responsiveness (Mobile & Tablet) ────────────────────────────────── */
@media (max-width: 900px) {
    .risk-intell-header-title { font-size: 1.1rem; letter-spacing: 0; }
    .risk-intell-header-sub { font-size: 0.65rem; }
    div[data-testid="stHorizontalBlock"]:has(.risk-intell-header-left) {
        padding: 0.5rem 1rem !important;
        flex-wrap: nowrap !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.risk-intell-header-left) > div[data-testid="column"] {
        min-width: auto !important;
        width: auto !important;
        flex: 1 1 auto !important;
    }
    .risk-intell-footer {
        flex-direction: column;
        justify-content: center;
        padding: 0.5rem;
        gap: 0.3rem;
    }
    .risk-intell-footer-security { display: none; }
    .risk-intell-footer-links { gap: 10px; flex-wrap: wrap; justify-content: center; }
    [data-testid="stAppViewBlockContainer"] { padding-top: 80px !important; }
}
@media (max-width: 600px) {
    .risk-intell-header-sub { display: none; }
    .risk-intell-header-title { font-size: 1rem; }
    div[data-testid="stHorizontalBlock"]:has(.risk-intell-header-left) { padding: 0.5rem !important; }
    .risk-intell-footer-brand { font-size: 0.85rem; }
    .risk-intell-footer-copy { font-size: 0.75rem; }
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
def init_session():
    qp_logged = st.query_params.get("logged_in") == "true"
    qp_user_id = st.query_params.get("user_id")
    qp_username = st.query_params.get("username")
    qp_role = st.query_params.get("role", "ESGRC")
    
    defaults = {
        "logged_in":        qp_logged,
        "user_id":          qp_user_id,
        "username":         qp_username,
        "role":             qp_role,
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
        # ── Pipeline Automation ───────────────────────────────────────────
        "pipeline_csv_bytes":       None,
        "pipeline_json_data":       None,
        "pipeline_csv_filename":    "",
        "pipeline_json_filename":   "",
        "pipeline_json_bytes":      None,
        "pipeline_additional_csvs": {},
        "pipeline_work_dir":        None,
        "pipeline_running":         False,
        "pipeline_complete":        False,
        "pipeline_master_report":   "",
        "pipeline_step_results":    [],
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
        return """You are an expert RISK INTELL (Environmental, Social, Governance, Risk, and Compliance) Advisor.
You help users understand ESG frameworks, risk compliance management, audit preparedness, and industry standards.
Encourage them to upload their metrics CSV and config JSON files in the panel on the left to generate their interactive performance report.

IMPORTANT FORMATTING RULES:
- Keep responses extremely short, direct, and concise (under 120 words). No preamble or fluff.
- Do NOT use # headings or markdown symbols like ** or * in your response.
- Write in plain, clear, professional prose.
- Use plain numbered lists (1. 2. 3.) or simple bullet points with a dash (-) only.
- Be direct, professional, and helpful.
"""
    low_m  = "\n".join(f"  • {m['name']} ({m['id']}): {m['score']}" for m in ctx.get("low_metrics", []))
    low_g  = "\n".join(f"  • {g['name']} ({g['id']}): {g['score']}" for g in ctx.get("low_groups", []))
    low_sm = "\n".join(f"  • {s['name']} ({s['id']}): {s['score']}" for s in ctx.get("low_sub_modules", []))
    return f"""You are an expert RISK INTELL analyst embedded in a professional reporting platform.

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
{str(ctx.get("report_text", ""))[:80000] + ("..." if len(str(ctx.get("report_text", ""))) > 80000 else "")}

IMPORTANT FORMATTING RULES:
- Keep responses extremely short, direct, and concise (under 120 words). No preamble or fluff.
- Do NOT use # headings or markdown symbols like ** or * in your response.
- Write in plain, clear, professional prose.
- Use plain numbered lists (1. 2. 3.) or simple bullet points with a dash (-) only.
- Be direct, professional, and helpful.
"""

def stream_groq(messages: list, system: str):
    """Generator that yields text tokens from Groq streaming API."""
    from groq import Groq
    client = Groq(api_key=st.secrets.get("GROQ_API_KEY", ""))
    
    # Groq needs system prompt as a message
    groq_msgs = [{"role": "system", "content": system}] + messages
    
    stream = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=groq_msgs,
        stream=True,
        max_tokens=1024,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content


# ─────────────────────────────────────────────────────────────────────────────
# AUTH SCREEN
# ─────────────────────────────────────────────────────────────────────────────
def render_auth():
    st.markdown("""
    <style>
    [data-testid="stApp"] {
        background: radial-gradient(circle at 50% -20%, #0D6F73 0%, #06363D 40%, #02181B 100%) !important;
    }
    [data-testid="stAppViewBlockContainer"] {
        background: transparent !important;
        padding-top: 10vh !important;
        min-height: 100vh;
        max-width: 100% !important;
    }
    .auth-title {
        font-size: 3.5rem;
        font-weight: 900;
        color: #FFFFFF;
        text-align: center;
        letter-spacing: -1px;
        margin-bottom: 0.5rem;
    }
    .auth-subtitle {
        font-size: 1.25rem;
        color: #84BABF;
        text-align: center;
        margin-bottom: 3rem;
        font-weight: 500;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    }
    div[data-testid="stTabs"] {
        background: #FFFFFF;
        padding: 2.5rem;
        border-radius: 16px;
        box-shadow: 0 20px 50px rgba(0,0,0,0.5);
    }
    header[data-testid="stHeader"] { display: none !important; }
    </style>
    
    <div class="auth-title">RISK INTELL Platform</div>
    <div class="auth-subtitle">
        Empower your enterprise with autonomous AI-driven ESG analytics, continuous risk compliance, and intelligent performance reporting.
    </div>
    """, unsafe_allow_html=True)

    _, col_m, _ = st.columns([1, 1.2, 1])
    
    with col_m:
        tab_in, tab_reg = st.tabs(["Sign In", "Create Account"])

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
                        st.session_state.role      = res["user"].get("role", "ESGRC")
                        st.query_params["logged_in"] = "true"
                        st.query_params["user_id"]   = str(res["user"]["_id"])
                        st.query_params["username"]  = res["user"]["username"]
                        st.query_params["role"]      = st.session_state.role
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error(res["error"])

        with tab_reg:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("reg_form"):
                rr = st.radio("Select Role", ["ESGRC", "APEX"], horizontal=True, key="rr")
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
                    res = register_user(ru, re_, rp, rr)
                    if res["ok"]:
                        st.success("Account created! Please sign in.")
                    else:
                        st.error(res["error"])


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(f"""
<div style="padding:0.8rem 0 0.5rem;">
    <div style="font-size:0.9rem; opacity:0.75; text-transform:uppercase; letter-spacing:0.1em;">Signed in as</div>
    <div style="font-size:1.3rem; font-weight:700; margin-top:3px;">{st.session_state.username}</div>
    <div style="font-size:1.1rem; color:#84BABF; font-weight:600; margin-top:4px;">Role: {st.session_state.role}</div>
</div>""", unsafe_allow_html=True)

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
    now_str = datetime.now().strftime("%d %b %Y  ·  %H:%M:%S")
    user    = st.session_state.get("username", "")

    st.markdown('<br>', unsafe_allow_html=True)
    hc1, hc2 = st.columns([10, 2], vertical_alignment="center")
    
    with hc1:
        st.markdown(f"""
        <div class="risk-intell-header-left">
            <div>
                <div class="risk-intell-header-title">RISK INTELL Platform</div>
                <div class="risk-intell-header-sub">Enterprise ESG &nbsp;·&nbsp; Risk &nbsp;·&nbsp; Compliance — Performance Analysis &amp; AI Reporting</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with hc2:
        user_name = st.session_state.get("username", "User")
        user_role = st.session_state.get("role", "")
        role_display = f'<span style="opacity: 0.7; font-size: 0.8rem;">({user_role})</span>' if user_role else ''
        
        st.markdown(f"""
        <div style="text-align: right; margin-bottom: 8px; display: flex; justify-content: flex-end; align-items: center; gap: 8px;">
            <div style="color: white; font-size: 0.95rem; margin-right: 10px;">
                Welcome, <b>{user_name}</b> {role_display}
            </div>
            <div class="risk-intell-header-badge"><span class="risk-intell-header-dot"></span> Live</div>
            <div class="risk-intell-header-date" id="live-clock">{now_str}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("Log Out", key="header_signout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.query_params.clear()
            st.rerun()
            
    st.markdown("""
<iframe srcdoc="
    <script>
        function updateClock() {{
            const clockEl = window.parent.document.getElementById('live-clock');
            if (clockEl) {{
                const now = new Date();
                const pad = (n) => String(n).padStart(2, '0');
                const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                const dateStr = pad(now.getDate()) + ' ' + months[now.getMonth()] + ' ' + now.getFullYear();
                const timeStr = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
                clockEl.innerHTML = dateStr + '  ·  ' + timeStr;
            }}
        }}
        if (!window.parent.clockInterval) {{
            window.parent.clockInterval = setInterval(updateClock, 1000);
        }}
        updateClock();
    </script>
" style="display:none;"></iframe>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
def render_footer():
    st.markdown("""
<div class="risk-intell-footer">
    <div>
        <div class="risk-intell-footer-brand">🛡️ RISK INTELL Platform</div>
        <div class="risk-intell-footer-copy">© 2024 RISK INTELL · All rights reserved · v2.0</div>
    </div>
    <div class="risk-intell-footer-security">
        🔒 End-to-end secure &nbsp;·&nbsp; Data stored in your MongoDB instance
    </div>
    <div class="risk-intell-footer-links">
        <span class="risk-intell-footer-link">Enterprise ESG</span>
        <span class="risk-intell-footer-link">Risk Management</span>
        <span class="risk-intell-footer-link">Compliance</span>
        <span class="risk-intell-footer-link">AI Analytics</span>
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
        st.markdown('<div style="color:#64748B; font-size:0.82rem; padding-top:0.65rem;">Runs the full RISK INTELL weighted-average pipeline and identifies the lowest-performing metrics, groups, and sub-modules.</div>', unsafe_allow_html=True)


def render_generating():
    st.markdown('<div class="sec-header"><span>⚙️</span><span class="sec-header-text">Generating Report…</span></div>', unsafe_allow_html=True)
    prog   = st.progress(0, text="Initialising RISK INTELL engine…")
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
                model="claude-3-7-sonnet-latest",
                max_tokens=250,
                system=system,
                messages=[{"role": "user", "content": "Please provide a comprehensive  executive summary (under 2 pages ) of the report's findings, highlighting the most critical areas needing attention based on the low-performing metrics, groups, and sub-modules."}]
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
                file_name=f"RISK INTELL_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
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
    <b>General RISK INTELL Assistant</b> &nbsp;·&nbsp;
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
            full_response = st.write_stream(stream_groq(claude_msgs, system_prompt))

        messages.append({"role": "assistant", "content": full_response})
        st.session_state.chat_messages = messages
        if st.session_state.report_id:
            append_chat_message(st.session_state.report_id, "assistant", full_response)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE AUTOMATION  — helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _get_pipeline_work_dir() -> str:
    """Get or create a persistent temp directory for this pipeline session."""
    if (st.session_state.pipeline_work_dir
            and os.path.exists(st.session_state.pipeline_work_dir)):
        return st.session_state.pipeline_work_dir
    work_dir = tempfile.mkdtemp(prefix="esgrc_pipeline_")
    st.session_state.pipeline_work_dir = work_dir
    return work_dir


def _execute_pipeline_step(step_id: str, work_dir: str, csv_bytes: bytes,
                            json_data: dict, additional_csvs: dict):
    """Route step_id → the correct pipeline_engine function."""
    from utils.pipeline_engine import (
        run_step1_low_performance_esgrc, run_step2_split_esgrc,
        run_step3_spc_fmea_esgrc,       run_step4_correlation_chaid_esgrc,
        run_step5_regression_esgrc,      run_step6_all_module_consolidation,
        run_step7_spc_fmea_l0,          run_step8_correlation_chaid_l0,
        run_step9_regression_l0,         run_final_report_combiner,
    )
    dispatch = {
        "step1": lambda: run_step1_low_performance_esgrc(work_dir, csv_bytes, json_data),
        "step2": lambda: run_step2_split_esgrc(work_dir, json_data),
        "step3": lambda: run_step3_spc_fmea_esgrc(work_dir),
        "step4": lambda: run_step4_correlation_chaid_esgrc(work_dir),
        "step5": lambda: run_step5_regression_esgrc(work_dir, json_data),
        "step6": lambda: run_step6_all_module_consolidation(work_dir, additional_csvs),
        "step7": lambda: run_step7_spc_fmea_l0(work_dir),
        "step8": lambda: run_step8_correlation_chaid_l0(work_dir),
        "step9": lambda: run_step9_regression_l0(work_dir),
        "final": lambda: run_final_report_combiner(work_dir),
    }
    fn = dispatch.get(step_id)
    if fn is None:
        return False, {}, f"Unknown step id: {step_id}"
    return fn()


def _step_card_html(step: dict, state: str, message: str) -> str:
    """Return styled HTML for one pipeline step row."""
    palette = {
        "pending": ("#F8FAFC", "#CBD5E1", "#0F172A", "#94A3B8", ""),
        "running": ("#FFFBEB", "#F59E0B", "#92400E", "#92400E",
                    "class=\"pipeline-running-row\""),
        "done":    ("#F0FFF4", "#10B981", "#0F172A", "#065F46", ""),
        "error":   ("#FFF5F5", "#EF4444", "#0F172A", "#7F1D1D", ""),
    }
    icons = {"pending": "⬜", "running": "🔄", "done": "✅", "error": "❌"}
    bg, border, title_c, msg_c, div_cls = palette.get(state, palette["pending"])
    icon = icons.get(state, "⬜")
    return (
        f'<div {div_cls} style="background:{bg};border:1px solid #E2E8F0;'
        f'border-left:4px solid {border};border-radius:8px;'
        f'padding:0.65rem 1rem;margin-bottom:0.42rem;">'
        f'<div style="font-size:0.8rem;font-weight:700;color:{title_c};">'
        f'{icon}&nbsp; Script&nbsp;{step["number"]} — {step["name"]}</div>'
        f'<div style="font-size:0.71rem;color:{msg_c};margin-top:3px;">{message}</div>'
        f'</div>'
    )


def _render_step_grid_preview(steps: list):
    """Render all steps as a 2-column pending grid."""
    cols = st.columns(2)
    for i, step in enumerate(steps):
        with cols[i % 2]:
            st.markdown(
                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                f'border-left:3px solid #94A3B8;border-radius:8px;'
                f'padding:0.6rem 0.85rem;margin-bottom:0.45rem;">'
                f'<div style="font-size:0.77rem;font-weight:700;color:#0369A1;">'
                f'Script {step["number"]} &mdash; {step["name"]}</div>'
                f'<div style="font-size:0.7rem;color:#64748B;margin-top:2px;">'
                f'{step["description"]}</div></div>',
                unsafe_allow_html=True,
            )


def _run_full_pipeline():
    """Execute all 10 pipeline steps with live progress UI update."""
    csv_bytes       = st.session_state.pipeline_csv_bytes
    json_data       = st.session_state.pipeline_json_data
    additional_csvs = dict(st.session_state.pipeline_additional_csvs)

    work_dir = _get_pipeline_work_dir()

    # ── Pre-write required input files ───────────────────────────────────────
    with open(os.path.join(work_dir, "input_metric_values_esgrc.csv"), "wb") as f:
        f.write(csv_bytes)
    with open(os.path.join(work_dir, "esgrc_performance_json_file.json"), "w",
              encoding="utf-8") as f:
        json.dump(json_data, f)

    # Copy built-in mapping / matrix if not user-provided
    for fname in ["module_mapping.csv", "module_matrix.csv"]:
        if fname not in additional_csvs:
            src = os.path.join("utils", fname)
            if os.path.exists(src):
                with open(src, "rb") as f:
                    additional_csvs[fname] = f.read()

    # ── UI scaffolding ────────────────────────────────────────────────────────
    st.markdown(
        '<div class="sec-header"><span>⚙️</span>'
        '<span class="sec-header-text">Running Pipeline — Live Progress</span></div>',
        unsafe_allow_html=True,
    )
    progress_bar = st.progress(0, text="Initialising pipeline…")
    total = len(PIPELINE_STEPS)

    # Create one empty slot per step
    slots = [st.empty() for _ in PIPELINE_STEPS]
    for i, step in enumerate(PIPELINE_STEPS):
        slots[i].markdown(
            _step_card_html(step, "pending", "Waiting…"),
            unsafe_allow_html=True,
        )

    # ── Execute every step ────────────────────────────────────────────────────
    results, all_ok = [], True
    for i, step in enumerate(PIPELINE_STEPS):
        slots[i].markdown(
            _step_card_html(step, "running", "Running…"),
            unsafe_allow_html=True,
        )
        progress_bar.progress(i / total,
                              text=f"Script {step['number']}/{total}: {step['name']}…")

        success, outputs, message = _execute_pipeline_step(
            step["id"], work_dir, csv_bytes, json_data, additional_csvs
        )
        if not success:
            all_ok = False

        state = "done" if success else "error"
        slots[i].markdown(
            _step_card_html(step, state, message),
            unsafe_allow_html=True,
        )
        results.append({"step": step, "success": success,
                         "outputs": outputs, "message": message})

    progress_bar.progress(1.0, text="✅ Pipeline complete!")

    # ── Persist results ───────────────────────────────────────────────────────
    master = next(
        (r["outputs"].get("master_content", "")
         for r in results if r["step"]["id"] == "final" and r["success"]),
        ""
    )
    st.session_state.pipeline_step_results  = results
    st.session_state.pipeline_complete      = True
    st.session_state.pipeline_master_report = master

    if all_ok:
        st.success("🎉 All 10 pipeline steps completed successfully!")
    else:
        failed = sum(1 for r in results if not r["success"])
        st.warning(f"⚠️ Pipeline complete with {failed} step(s) that encountered errors.")

    time.sleep(0.6)
    st.rerun()


def _render_pipeline_results():
    """Show step results, master report preview, and all download buttons."""
    results  = st.session_state.pipeline_step_results
    work_dir = st.session_state.pipeline_work_dir
    master   = st.session_state.pipeline_master_report
    passed   = sum(1 for r in results if r["success"])
    failed   = len(results) - passed

    # ── Summary hero ──────────────────────────────────────────────────────────
    hero_grad = ("0C4A6E,#0369A1" if failed == 0 else "92400E,#B45309")
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#{hero_grad});'
        f'border-radius:14px;padding:1.4rem 1.8rem;color:white;'
        f'margin-bottom:1.2rem;box-shadow:0 4px 20px rgba(3,105,161,0.25);">'
        f'<div style="font-size:1.1rem;font-weight:800;">🎯 Pipeline Complete</div>'
        f'<div style="font-size:0.85rem;opacity:0.9;margin-top:6px;">'
        f'✅ {passed} steps passed &nbsp;·&nbsp; '
        f'{"✅ 0 failed" if failed == 0 else f"❌ {failed} failed"}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Step-by-step results ──────────────────────────────────────────────────
    st.markdown(
        '<div class="sec-header"><span>📋</span>'
        '<span class="sec-header-text">Step-by-Step Results</span></div>',
        unsafe_allow_html=True,
    )
    for r in results:
        st.markdown(
            _step_card_html(r["step"], "done" if r["success"] else "error", r["message"]),
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Master report ─────────────────────────────────────────────────────────
    st.markdown(
        '<div class="sec-header"><span>📄</span>'
        '<span class="sec-header-text">Master Consolidated Report</span></div>',
        unsafe_allow_html=True,
    )
    col_dl, col_info, _ = st.columns([1.4, 2.5, 1])
    with col_dl:
        if master:
            st.download_button(
                label="⬇️  Download Master Report (.txt)",
                data=master,
                file_name=(f"MASTER_CONSOLIDATED_REPORT_"
                           f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"),
                mime="text/plain",
                use_container_width=True,
            )
            try:
                from utils.master_pdf import generate_master_pdf_bytes
                pdf_bytes = generate_master_pdf_bytes(master)
                st.download_button(
                    label="⬇️  Download Master Report (.pdf)",
                    data=pdf_bytes,
                    file_name=(f"MASTER_CONSOLIDATED_REPORT_"
                               f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"),
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Error generating PDF: {e}")
        else:
            st.warning("Master report not generated.")
    with col_info:
        st.markdown(
            '<div style="color:#64748B;font-size:0.8rem;padding-top:0.65rem;">'
            '📄 Single text file combining all analysis reports — '
            'ready for AI processing.</div>',
            unsafe_allow_html=True,
        )

    if master:
        with st.expander("📖 Preview Master Report", expanded=False):
            st.text_area("Master Report", master, height=420,
                         label_visibility="collapsed")

    st.divider()

    # ── Individual file downloads ─────────────────────────────────────────────
    st.markdown(
        '<div class="sec-header"><span>📁</span>'
        '<span class="sec-header-text">Download Individual Output Files</span></div>',
        unsafe_allow_html=True,
    )

    if work_dir and os.path.exists(work_dir):
        all_f   = sorted(os.listdir(work_dir))
        txt_f   = [f for f in all_f if f.endswith(".txt")
                   and f != "MASTER_CONSOLIDATED_REPORT.txt"]
        pdf_f   = [f for f in all_f if f.endswith(".pdf")]
        csv_f   = [f for f in all_f if f.endswith(".csv")]

        tab_txt, tab_pdf, tab_csv = st.tabs(
            [f"📄 Text Reports ({len(txt_f)})",
             f"📊 PDF Charts ({len(pdf_f)})",
             f"🗂 CSV Data ({len(csv_f)})"]
        )

        for file_list, tab_widget, mime_type in [
            (txt_f, tab_txt, "text/plain"),
            (pdf_f, tab_pdf, "application/pdf"),
            (csv_f, tab_csv, "text/csv"),
        ]:
            with tab_widget:
                if not file_list:
                    st.info("No files of this type were generated.")
                else:
                    dl_cols = st.columns(2)
                    for j, fname in enumerate(file_list):
                        fpath = os.path.join(work_dir, fname)
                        try:
                            with open(fpath, "rb") as fh:
                                fdata = fh.read()
                            with dl_cols[j % 2]:
                                st.download_button(
                                    label=f"⬇️  {fname}",
                                    data=fdata,
                                    file_name=fname,
                                    mime=mime_type,
                                    key=f"dl_{fname}_{j}",
                                    use_container_width=True,
                                )
                        except Exception as e:
                            with dl_cols[j % 2]:
                                st.error(f"Could not read {fname}: {e}")

    st.divider()
    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if st.button("🔁  Run Pipeline Again", use_container_width=True):
            st.session_state.pipeline_complete      = False
            st.session_state.pipeline_step_results  = []
            st.session_state.pipeline_master_report = ""
            st.session_state.pipeline_work_dir      = None
            st.rerun()


def render_pipeline_tab():
    """Full Pipeline Automation tab — Tab 2."""
    from utils.pipeline_flows import render_esgrc_pipeline, render_apex_pipeline
    
    role = st.session_state.get("role", "ESGRC")
    
    if role == "APEX":
        render_apex_pipeline()
    else:
        render_esgrc_pipeline()


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

    # ── Main Layout (No Chat Sidebar) ─────────────────────────────────────────
    # Top Navigation Menu
    nav_home, nav_get_started, nav_docs, nav_contact, nav_more = st.tabs([
        "Home", "Get Started", "Docs", "Contact Us", "More"
    ])

    with nav_home:
        # Hero Landing Page
        role = st.session_state.get("role", "ESGRC")
        if role == "APEX":
            hero_title = "Enterprise Risk Monitoring"
            hero_subtitle = "Transform your business with intelligent risk analysis and predictive insights."
        else:
            hero_title = "Supplier ESG Management"
            hero_subtitle = "Align supply chain reporting to your sustainability goals and close regulatory gaps."

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #06363D 0%, #085558 100%); 
                    border-radius: 0px; padding: 5rem 3rem; text-align: center; color: white;
                    margin-top: 1rem; margin-bottom: 2rem; box-shadow: 0 10px 30px rgba(6,54,61,0.4);
                    position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; width: 100vw;">
            <div style="font-size: 3rem; font-weight: 800; margin-bottom: 1rem;">{hero_title}</div>
            <div style="font-size: 1.2rem; opacity: 0.9; max-width: 800px; margin: 0 auto 2.5rem auto; line-height: 1.6;">
                {hero_subtitle}
            </div>
            <div style="display: flex; justify-content: center; gap: 1rem;">
                <button id="get-started-btn"
                        style="background: #0D6F73; color: white; border: none; padding: 0.8rem 2.5rem; border-radius: 30px; font-weight: 600; font-size: 1.2rem; cursor: pointer; transition: all 0.3s; box-shadow: 0 4px 15px rgba(13,111,115,0.4);">
                    Get Started →
                </button>
            </div>
            <div style="margin-top: 4rem; display: flex; justify-content: center; gap: 4rem; opacity: 0.8;">
                <div><div style="font-size: 2.5rem; font-weight: 700;">+200%</div><div style="font-size: 1rem;">Performance Boost</div></div>
                <div><div style="font-size: 2.5rem; font-weight: 700;">+40x</div><div style="font-size: 1rem;">Faster Analysis</div></div>
                <div><div style="font-size: 2.5rem; font-weight: 700;">+345%</div><div style="font-size: 1rem;">ROI Increase</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        import streamlit.components.v1 as components
        components.html("""
        <script>
        const doc = window.parent.document;
        let checkExist = setInterval(function() {
            const btn = doc.getElementById('get-started-btn');
            if (btn && !btn.dataset.bound) {
                btn.dataset.bound = "true";
                btn.addEventListener('click', function() {
                    const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
                    if (tabs.length > 1) {
                        tabs[1].click();
                    }
                });
                clearInterval(checkExist);
            }
        }, 100);
        </script>
        """, height=0, width=0)

    with nav_get_started:
        # Legacy Standard Report Tab + Pipeline
        render_pipeline_tab()

    with nav_docs:
        st.markdown("### Documentation")
        st.write("Welcome to the Risk Intell platform documentation. Guides and API references will be available here.")

    with nav_contact:
        st.markdown("### Contact Us")
        st.write("Reach out to our enterprise support team for assistance.")

    with nav_more:
        st.markdown("### More")
        st.write("Settings and additional configurations.")

    # ── Page footer ──────────────────────────────────────────────────────────
    render_footer()


if __name__ == "__main__":
    main()
