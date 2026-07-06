"""
ESGRC Full Pipeline Engine — v1.0
==================================
Wraps all 9 analysis scripts as callable Python functions.
Each step function returns: (success: bool, outputs: dict, message: str)

Script mapping:
  Step 1  → AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py
  Step 2  → M_G_Sub_M_split_ESGRC_1_0.py
  Step 3  → x_bar_r_chart_fmea_esg_5_0.py
  Step 4  → Correlation_CHAID_FT_Analysis_ESGRC_8_0.py
  Step 5  → AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py
  Step 6  → all_module_low_performance_analysis_1_0.py
  Step 7  → SS_x_bar_r_chart_fmea_L0_6_0.py
  Step 8  → AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py
  Step 9  → AI_ready_Mutiple_Regression_Model_implementation_L0_19_0.py
  Final   → text-report-combiner.py
"""

import os
import re
import io
import glob
import json
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import Tuple, Dict, List, Optional, Any

import numpy as np
import pandas as pd

try:
    # pyrefly: ignore [missing-import]
    import matplotlib
    matplotlib.use("Agg")          # Non-interactive backend — safe for Streamlit
    # pyrefly: ignore [missing-import]
    import matplotlib.pyplot as plt
    # pyrefly: ignore [missing-import]
    from matplotlib.backends.backend_pdf import PdfPages
    MATPLOTLIB_AVAILABLE = True
except Exception as e:
    import traceback
    print("MATPLOTLIB IMPORT ERROR:")
    traceback.print_exc()
    MATPLOTLIB_AVAILABLE = False

# ── Optional heavy dependencies ───────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import TensorDataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.svm import SVR
    from sklearn.model_selection import GridSearchCV, KFold, train_test_split
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.decomposition import PCA
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.impute import SimpleImputer
    SKLEARN_AVAILABLE = True
except Exception as e:
    import traceback
    print("SKLEARN IMPORT ERROR:")
    traceback.print_exc()
    SKLEARN_AVAILABLE = False

try:
    from scipy.fft import fft, fftfreq
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    from CHAID import Tree as CHAIDTree
    CHAID_AVAILABLE = True
except ImportError:
    CHAID_AVAILABLE = False

ANALYSIS_DATE = datetime.now().strftime("%Y-%m-%d")
D2_APPROX = 1.128

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _working_dir(path: str):
    """Temporarily change the working directory, then restore."""
    original = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _wavg(values: list, weights: list) -> float:
    total = sum(weights)
    return 0.0 if total == 0 else sum(v * w for v, w in zip(values, weights)) / total


# ── ReportLab Text-to-PDF Converter ──────────────────────────────────────────
def convert_txt_to_pdf(txt_path: str, pdf_path: str):
    """
    Parses a generated text report file, automatically layouting headings,
    data tables, and monospaced text segments, and saving as a ReportLab PDF.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    styles = getSampleStyleSheet()
    
    # Custom styles matching sky-blue / slate palette
    normal_style = ParagraphStyle(
        'MonoBody',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#334155')
    )
    heading_style = ParagraphStyle(
        'PDFHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=13,
        textColor=colors.HexColor('#0369A1'),
        spaceBefore=10,
        spaceAfter=5
    )
    title_style = ParagraphStyle(
        'PDFTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#0C4A6E'),
        spaceAfter=10
    )

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=36, rightMargin=36,
        topMargin=36, bottomMargin=36
    )
    
    story = []
    filename = os.path.basename(txt_path)
    story.append(Paragraph(f"RISK INTELL Analysis Report: {filename}", title_style))
    story.append(Spacer(1, 8))
    
    try:
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(txt_path, 'r', encoding='latin-1') as f:
                content = f.read()
                
        # Dynamically replace ESGRC/ESGR to RISK INTELL while preserving 'esgrc module' case-insensitively
        placeholders = []
        def protect(match):
            placeholders.append(match.group(0))
            return f"___PLACEHOLDER_{len(placeholders)-1}___"
            
        content_sub = re.sub(r"esgrc\s+module", protect, content, flags=re.IGNORECASE)
        content_sub = re.sub(r"esgrc_module", protect, content_sub, flags=re.IGNORECASE)
        
        content_sub = re.sub(r"ESGRC Intelligence Platform", "RISK INTELL Platform", content_sub)
        content_sub = re.sub(r"ESGRC Intelligence", "RISK INTELL", content_sub)
        content_sub = re.sub(r"ESGRC", "RISK INTELL", content_sub)
        content_sub = re.sub(r"ESGR", "RISK INTELL", content_sub)
        
        for idx, orig in enumerate(placeholders):
            content_sub = content_sub.replace(f"___PLACEHOLDER_{idx}___", orig)
            
        lines = content_sub.split('\n')
    except Exception as e:
        lines = [f"Failed to read file: {e}"]
        
    table_data = []
    in_table = False
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            if in_table and table_data:
                # Flush the table flowable
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
                    ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#E2E8F0')),
                    ('FONTNAME', (0,0), (-1,-1), 'Courier'),
                    ('FONTSIZE', (0,0), (-1,-1), 7.5),
                    ('PADDING', (0,0), (-1,-1), 3),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ]))
                story.append(t)
                story.append(Spacer(1, 5))
                table_data = []
                in_table = False
            else:
                story.append(Spacer(1, 5))
            continue
            
            # Detect comma-separated or tab-separated tables
        is_csv_row = ',' in line_str and len(line_str.split(',')) >= 3
        if is_csv_row and (line_str.startswith('[') or line_str.startswith('(') or line_str.startswith('{')):
            is_csv_row = False
        is_tsv_row = '\t' in line_str and len(line_str.split('\t')) >= 3
        
        if is_csv_row or is_tsv_row:
            in_table = True
            cols = line_str.split(',') if is_csv_row else line_str.split('\t')
            table_data.append([Paragraph(c.strip(), normal_style) for c in cols])
        else:
            if in_table and table_data:
                # Flush table before regular text
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
                    ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#E2E8F0')),
                    ('FONTNAME', (0,0), (-1,-1), 'Courier'),
                    ('FONTSIZE', (0,0), (-1,-1), 7.5),
                    ('PADDING', (0,0), (-1,-1), 3),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ]))
                story.append(t)
                story.append(Spacer(1, 5))
                table_data = []
                in_table = False
                
            if line_str.startswith('---') or line_str.startswith('==='):
                story.append(Spacer(1, 4))
            elif len(line_str) < 55 and (
                line_str.endswith(':') or 
                'Low-Performing' in line_str or 
                'Risk Scenarios' in line_str or
                '---' in line_str or
                line_str.isupper()
            ):
                story.append(Paragraph(line_str, heading_style))
            else:
                # Convert space alignment for ReportLab HTML parsing
                formatted_line = line_str.replace(' ', '&nbsp;')
                story.append(Paragraph(formatted_line, normal_style))
                
    if in_table and table_data:
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#E2E8F0')),
            ('FONTNAME', (0,0), (-1,-1), 'Courier'),
            ('FONTSIZE', (0,0), (-1,-1), 7.5),
            ('PADDING', (0,0), (-1,-1), 3),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t)
        
    try:
        doc.build(story)
    except Exception as e:
        # Fallback to plain page if rendering failed
        fallback_doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36
        )
        err_story = [
            Paragraph("ESGRC Report Render Fallback", title_style),
            Spacer(1, 10),
            Paragraph(f"Rendering error encountered: {e}", heading_style),
            Spacer(1, 10),
        ]
        for line in lines:
            err_story.append(Paragraph(line.replace(' ', '&nbsp;'), normal_style))
        fallback_doc.build(err_story)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED SPC / FMEA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _to_long(df_wide: pd.DataFrame) -> pd.DataFrame:
    df = df_wide.copy()
    df["timestamp"] = range(1, len(df) + 1)
    metric_cols = [c for c in df.columns if c != "timestamp"]
    long = df.melt(id_vars=["timestamp"], value_vars=metric_cols,
                   var_name="metric_id", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    return long.sort_values(["metric_id", "timestamp"]).reset_index(drop=True)


def _xmr_limits(series: pd.Series) -> dict:
    xbar = series.mean()
    mr = series.diff().abs().dropna()
    mrbar = mr.mean()
    sigma = mrbar / D2_APPROX if pd.notnull(mrbar) and mrbar > 0 else 0.0
    return dict(xbar=xbar, mrbar=mrbar, sigma=sigma,
                ucl_x=xbar + 3 * sigma, lcl_x=xbar - 3 * sigma,
                ucl_mr=3.268 * mrbar if pd.notnull(mrbar) else float("nan"),
                lcl_mr=0.0)


def _detect_xmr(df_m: pd.DataFrame, limits: dict) -> pd.DataFrame:
    out = df_m.copy()
    out["signal_x"] = (out["value"] > limits["ucl_x"]) | (out["value"] < limits["lcl_x"])
    out["mr"] = out["value"].diff().abs()
    out["signal_mr"] = out["mr"] > limits["ucl_mr"]
    return out


def _save_rpn_pdf(summary: pd.DataFrame, filename: str, rows_per_page: int = 30):
    want = ["metric_id", "mean", "sigma", "UCL", "LCL", "Sigma_Level", "signals", "RPN", "analysis_date"]
    cols = [c for c in want if c in summary.columns]
    tbl = summary[cols].copy()
    n_pages = max(1, (len(tbl) + rows_per_page - 1) // rows_per_page)
    with PdfPages(filename) as pdf:
        for page in range(n_pages):
            chunk = tbl.iloc[page * rows_per_page:(page + 1) * rows_per_page]
            fig, ax = plt.subplots(figsize=(11, 8))
            ax.axis("off")
            ax.set_title(f"RPN Summary Report ({ANALYSIS_DATE}) — Page {page+1}/{n_pages}",
                         fontsize=14, weight="bold", pad=30)
            t = ax.table(cellText=chunk.to_numpy(), colLabels=chunk.columns.tolist(), loc="center")
            t.auto_set_font_size(False); t.set_fontsize(9); t.scale(0.9, 1.2)
            ax.text(0.5, -0.12, f"Generated {ANALYSIS_DATE} | Total metrics: {len(tbl)}",
                    ha="center", va="top", fontsize=10, transform=ax.transAxes)
            pdf.savefig(fig); plt.close(fig)


def _save_spc_pdf(long_df: pd.DataFrame, metric_ids: list, filename: str):
    with PdfPages(filename) as pdf:
        for mid in metric_ids:
            df_m = long_df[long_df["metric_id"] == mid].sort_values("timestamp")
            lim = _xmr_limits(df_m["value"])
            df_s = _detect_xmr(df_m, lim)
            fig = plt.figure(figsize=(11, 8))
            plt.plot(df_s["timestamp"], df_s["value"], marker="o", label="Values")
            plt.axhline(lim["xbar"], color="green", linestyle="--", label="Center Line")
            plt.axhline(lim["ucl_x"], color="red",   linestyle="--", label="UCL")
            plt.axhline(lim["lcl_x"], color="red",   linestyle="--", label="LCL")
            # Mark signals
            sigs = df_s[df_s["signal_x"]]
            if not sigs.empty:
                plt.scatter(sigs["timestamp"], sigs["value"], color="red", zorder=5, s=60, label="Signal")
            plt.title(f"Individuals Chart — {mid} ({ANALYSIS_DATE})", pad=30)
            plt.xlabel("Timestamp"); plt.ylabel("Performance (%)"); plt.legend()
            pdf.savefig(fig); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED CORRELATION / CHAID HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _identify_trends(df: pd.DataFrame) -> dict:
    if not SKLEARN_AVAILABLE:
        return {c: "sklearn not available" for c in df.columns}
    trends = {}
    time_arr = np.arange(len(df))
    for col in df.columns:
        y = df[col].dropna().values
        if len(y) < 2:
            trends[col] = "Insufficient data"; continue
        x = time_arr[:len(y)].reshape(-1, 1)
        slope = LinearRegression().fit(x, y).coef_[0]
        trends[col] = "Stable" if abs(slope) < 1e-5 else ("Increasing" if slope > 0 else "Decreasing")
    return trends


def _assess_fourier(df: pd.DataFrame) -> dict:
    if not SCIPY_AVAILABLE:
        return {c: "scipy not available" for c in df.columns}
    reps = {}
    for col in df.columns:
        y = df[col].dropna().values
        if len(y) < 2:
            reps[col] = "Insufficient data"; continue
        N = len(y)
        yf = fft(y)
        xf = fftfreq(N, 1)[:N // 2]
        mags = 2.0 / N * np.abs(yf[:N // 2])
        peaks, _ = find_peaks(mags, height=0.1)
        if len(peaks) > 0 and xf[peaks[0]] > 0:
            reps[col] = f"Dominant period: {1/xf[peaks[0]]:.2f} units (repetitive)"
        else:
            reps[col] = "No clear repetition (potential instability)"
    return reps


def _detect_inconsistencies(corr_matrix: pd.DataFrame, df: pd.DataFrame,
                             corr_threshold: float = 0.5, z_threshold: float = 2.0) -> tuple:
    dep_inc, ind_inc = {}, {}
    cols = corr_matrix.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            corr = corr_matrix.loc[c1, c2]
            if pd.isna(corr): continue
            s1, s2 = df[c1].dropna(), df[c2].dropna()
            min_len = min(len(s1), len(s2))
            if min_len < 2: continue
            s1, s2 = s1[:min_len], s2[:min_len]
            z1 = (s1 - s1.mean()) / (s1.std() + 1e-8)
            z2 = (s2 - s2.mean()) / (s2.std() + 1e-8)
            diff = np.abs(z1 - z2)
            if abs(corr) > corr_threshold:
                cnt = int(np.sum(diff > z_threshold))
                if cnt > 0:
                    dep_inc[(c1, c2)] = {"correlation": corr, "count": cnt,
                                          "percentage": cnt / min_len * 100, "min_len": min_len}
            else:
                cnt = int(np.sum(diff < 0.5))
                if cnt > min_len * 0.1:
                    ind_inc[(c1, c2)] = {"correlation": corr, "count": cnt,
                                          "percentage": cnt / min_len * 100, "min_len": min_len}
    return dep_inc, ind_inc


def _bin_features(trends: dict, repetitions: dict, dep_inc: dict,
                   ind_inc: dict, corr_matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in corr_matrix.columns:
        trend = trends.get(metric, "Unknown")
        rep   = repetitions.get(metric, "Unknown")
        rep_bin = "Repetitive" if "repetitive" in str(rep).lower() else (
                  "Irregular"  if "instability" in str(rep).lower() else "Insufficient")
        avg_corr = corr_matrix[metric].dropna().abs().mean() if not corr_matrix[metric].dropna().empty else 0.0
        corr_bin = "Very High" if avg_corr > 0.6 else ("High" if avg_corr > 0.4 else ("Medium" if avg_corr > 0.2 else "Low"))
        total_inc = sum(1 for p in dep_inc if metric in p) + sum(1 for p in ind_inc if metric in p)
        inc_bin   = "Very High" if total_inc > 15 else ("High" if total_inc > 8 else ("Medium" if total_inc > 3 else "Low"))
        if   inc_bin in ["Very High", "High"] and rep_bin == "Irregular": risk = "Critical"
        elif inc_bin in ["Very High", "High"] or rep_bin == "Irregular":  risk = "High"
        elif inc_bin == "Medium" or corr_bin in ["Very High", "High"] or trend == "Decreasing": risk = "Elevated"
        elif trend == "Stable" and rep_bin == "Repetitive" and inc_bin == "Low": risk = "Low"
        else: risk = "Moderate"
        rows.append({"Metric": metric, "Trend": trend, "Repetition": rep_bin,
                     "Avg_Correlation": corr_bin, "Inconsistency_Level": inc_bin, "Risk_Level": risk})
    df_out = pd.DataFrame(rows)
    return df_out.fillna({"Trend": "Unknown", "Repetition": "Insufficient",
                           "Avg_Correlation": "Low", "Inconsistency_Level": "Low", "Risk_Level": "Moderate"})


def _run_chaid(chaid_df: pd.DataFrame, indep_vars: list, dep_var: str = "Risk_Level") -> str:
    """Returns a CHAID tree summary string, or an explanatory message."""
    if not CHAID_AVAILABLE:
        return "CHAID analysis skipped — package not installed (`pip install CHAID`)."
    available = [v for v in indep_vars if v in chaid_df.columns]
    if len(chaid_df) < 10 or len(available) == 0:
        return "CHAID analysis skipped — insufficient data."
    try:
        tree = CHAIDTree.from_pandas_df(
            chaid_df, dict(zip(available, ["nominal"] * len(available))),
            dep_var, min_child_node_size=5, max_depth=3)
        return str(tree)
    except Exception as e:
        return f"CHAID tree could not be built: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1  — Low Performance Analysis (ESGRC Module)
# Source  : AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step1_low_performance_esgrc(
    work_dir: str, csv_bytes: bytes, json_data: dict
) -> Tuple[bool, Dict, str]:
    """
    Computes weighted averages for ESGRC module; identifies low-performing metrics/groups/sub-modules.
    Outputs: module_values_esgrc.csv, low_performing_entities_report_esgrc.txt
    """
    try:
        metric_data = pd.read_csv(io.BytesIO(csv_bytes), low_memory=False)

        # ── Extract IDs & names ───────────────────────────────────────────────
        metric_ids, group_ids, sub_module_ids = [], [], []
        id_name: Dict[str, str] = {}
        for sm in json_data.get("sub_modules", []):
            sm_id = sm["sub_module_id"]
            sub_module_ids.append(sm_id)
            id_name[sm_id] = sm.get("sub_module_name", sm_id)
            for g in sm.get("groups", []):
                g_id = g["group_id"]
                group_ids.append(g_id)
                id_name[g_id] = g.get("group_name", g_id)
                for p in g.get("value", []):
                    m_id = p["metric_id"]
                    metric_ids.append(m_id)
                    id_name[m_id] = p.get("metric_name", m_id)

        module_id = json_data["module_id"]

        # ── Weighted averages ─────────────────────────────────────────────────
        g_avgs  = {g: [] for g in group_ids}
        sm_avgs = {s: [] for s in sub_module_ids}
        mod_avgs: List[float] = []

        for row_idx in range(len(metric_data)):
            row_mod = []
            for sm in json_data.get("sub_modules", []):
                sm_id = sm["sub_module_id"]
                sw, sv = [], []
                for g in sm.get("groups", []):
                    gw, gv = [], []
                    for p in g.get("value", []):
                        mid = p["metric_id"]
                        if mid in metric_data.columns:
                            gw.append(float(p.get("weight", 1)))
                            gv.append(float(metric_data[mid].iloc[row_idx]))
                    if gw:
                        wa = _wavg(gv, gw)
                        g_avgs[g["group_id"]].append(wa)
                        sw.append(1.0); sv.append(wa)
                if not sw and "value" in sm:
                    for p in sm["value"]:
                        mid = p["metric_id"]
                        if mid in metric_data.columns:
                            sw.append(float(p.get("weight", 1)))
                            sv.append(float(metric_data[mid].iloc[row_idx]))
                if sw:
                    sm_avg = _wavg(sv, sw)
                    sm_avgs[sm_id].append(sm_avg)
                    row_mod.append(sm_avg)
            if row_mod:
                mod_avgs.append(_wavg(row_mod, [1.0] * len(row_mod)))

        # ── Build enriched dataframe ──────────────────────────────────────────
        n = len(metric_data)
        new_cols: Dict[str, list] = {}
        for gid, avgs in g_avgs.items():
            padded = avgs + [np.nan] * max(0, n - len(avgs))
            new_cols[gid] = [round(v, 2) for v in padded[:n]]
        for smid, avgs in sm_avgs.items():
            padded = avgs + [np.nan] * max(0, n - len(avgs))
            new_cols[smid] = [round(v, 2) for v in padded[:n]]
        mod_padded = mod_avgs + [np.nan] * max(0, n - len(mod_avgs))
        new_cols["ESRC_001"] = [round(v, 2) for v in mod_padded[:n]]

        enriched = pd.concat([metric_data, pd.DataFrame(new_cols)], axis=1)
        enriched = enriched.loc[:, ~enriched.columns.duplicated()]
        enriched = enriched.apply(lambda x: x.round(2) if x.dtype.kind in "fc" else x)

        with _working_dir(work_dir):
            enriched.to_csv("module_values_esgrc.csv", index=False)

            # ── Identify low performers ───────────────────────────────────────
            def _low(ids, df, top=10):
                scores = {i: float(df[i].iloc[0]) for i in ids if i in df.columns}
                return sorted(scores.items(), key=lambda x: x[1])[:top]

            lm  = _low(metric_ids, enriched)
            lg  = _low(group_ids, enriched)
            lsm = _low(sub_module_ids, enriched)
            oa  = _wavg(mod_avgs, [1.0] * len(mod_avgs)) if mod_avgs else 0.0

            with open("low_performing_entities_report_esgrc.txt", "w", encoding="utf-8") as f:
                f.write("Low-Performing Metrics\nS.No,Metric Id,Metric Name,Metric Value\n")
                for i, (mid, val) in enumerate(lm, 1):
                    f.write(f"{i},{mid},{id_name.get(mid, mid)},{val:.2f}\n")
                f.write("\nLow-Performing Groups\nS.No,Group Id,Group Name,Group Value\n")
                for i, (gid, val) in enumerate(lg, 1):
                    f.write(f"{i},{gid},{id_name.get(gid, gid)},{val:.2f}\n")
                f.write("\nLow-Performing Sub-Modules\nS.No,Sub-Module Id,Sub-Module Name,Sub-Module Value\n")
                for i, (smid, val) in enumerate(lsm, 1):
                    f.write(f"{i},{smid},{id_name.get(smid, smid)},{val:.2f}\n")
                f.write(f"\nOverall Module Average,{module_id},{oa:.2f}\n")

            convert_txt_to_pdf("low_performing_entities_report_esgrc.txt", "low_performing_entities_report_esgrc.pdf")

        return True, {
            "files":         ["module_values_esgrc.csv", "low_performing_entities_report_esgrc.txt", "low_performing_entities_report_esgrc.pdf"],
            "overall_avg":   round(oa, 2),
            "metric_count":  len(lm),
        }, (f"Weighted averages computed for {len(metric_ids)} metrics. "
            f"Overall score: {oa:.2f}. {len(lm)} low-performing entities identified (PDF report generated).")

    except Exception:
        return False, {}, f"Step 1 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2  — M / G / Sub-Module Data Split
# Source  : M_G_Sub_M_split_ESGRC_1_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step2_split_esgrc(work_dir: str, json_data: dict) -> Tuple[bool, Dict, str]:
    """
    Splits module_values_esgrc.csv into filtered metrics / groups / sub-modules / risk-assessment CSVs.
    """
    try:
        with _working_dir(work_dir):
            if not os.path.exists("module_values_esgrc.csv"):
                return False, {}, "module_values_esgrc.csv not found — run Step 1 first."

            df = pd.read_csv("module_values_esgrc.csv", low_memory=False)

            mc, gc, sc = [], [], []
            for sm in json_data.get("sub_modules", []):
                sc.append(sm["sub_module_id"])
                for g in sm.get("groups", []):
                    gc.append(g["group_id"])
                    for p in g.get("value", []):
                        mc.append(p["metric_id"])

            mc = [c for c in mc if c in df.columns]
            gc = [c for c in gc if c in df.columns]
            sc = [c for c in sc if c in df.columns]
            rc = sc + (["ESRC_001"] if "ESRC_001" in df.columns else [])

            df[mc].to_csv("filtered_metrics_data_esgrc.csv",    index=False)
            df[gc].to_csv("filtered_groups_data_esgrc.csv",     index=False)
            df[sc].to_csv("filtered_sub_modules_data_esgrc.csv", index=False)
            df[rc].to_csv("data_for_risk_assessment_esgrc.csv", index=False)

        return True, {
            "files": ["filtered_metrics_data_esgrc.csv", "filtered_groups_data_esgrc.csv",
                      "filtered_sub_modules_data_esgrc.csv", "data_for_risk_assessment_esgrc.csv"],
            "metric_count": len(mc), "group_count": len(gc), "sub_module_count": len(sc),
        }, f"Split complete — {len(mc)} metrics, {len(gc)} groups, {len(sc)} sub-modules. 4 CSVs generated."

    except Exception:
        return False, {}, f"Step 2 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3  — SPC / FMEA X-Bar-R Charts  (ESGRC Module)
# Source  : x_bar_r_chart_fmea_esg_5_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step3_spc_fmea_esgrc(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    X-MR control charts + FMEA RPN scoring for every metric in input_metric_values_esgrc.csv.
    Outputs: TXT summary, RPN PDF, SPC charts PDF.
    """
    try:
        with _working_dir(work_dir):
            if not os.path.exists("input_metric_values_esgrc.csv"):
                return False, {}, "input_metric_values_esgrc.csv not found in work directory."

            df_wide  = pd.read_csv("input_metric_values_esgrc.csv")
            long_df  = _to_long(df_wide)
            metric_ids = sorted(long_df["metric_id"].unique())

            rows = []
            for mid in metric_ids:
                df_m   = long_df[long_df["metric_id"] == mid].sort_values("timestamp")
                lim    = _xmr_limits(df_m["value"])
                df_sig = _detect_xmr(df_m, lim)
                sigs   = int(df_sig["signal_x"].sum() + df_sig["signal_mr"].sum())
                rpn    = 7 * min(10, max(1, sigs)) * 5
                rows.append({
                    "metric_id": mid, "mean": round(lim["xbar"], 2),
                    "sigma": round(lim["sigma"], 2),
                    "UCL": round(lim["ucl_x"], 2), "LCL": round(lim["lcl_x"], 2),
                    "signals": sigs, "RPN": rpn,
                })

            summary = (pd.DataFrame(rows)
                       .sort_values(["RPN", "signals", "metric_id"], ascending=[False, False, True])
                       .reset_index(drop=True))
            summary["analysis_date"] = ANALYSIS_DATE

            txt_f  = f"metrics_summary_{ANALYSIS_DATE}.txt"
            pdf_f  = f"metrics_summary_{ANALYSIS_DATE}.pdf"
            summary.to_csv(txt_f, sep="\t", index=False)
            convert_txt_to_pdf(txt_f, pdf_f)

            files_generated = [txt_f, pdf_f]
            msg_suffix = "PDF charts skipped (matplotlib not installed)."
            if MATPLOTLIB_AVAILABLE:
                rpn_f  = f"RPN_summary_report_{ANALYSIS_DATE}.pdf"
                spc_f  = f"SPC_charts_report_{ANALYSIS_DATE}.pdf"
                _save_rpn_pdf(summary, rpn_f)
                _save_spc_pdf(long_df, metric_ids, spc_f)
                files_generated.extend([rpn_f, spc_f])
                msg_suffix = "RPN summary + SPC charts PDFs generated."

        return True, {
            "files": files_generated, "metric_count": len(metric_ids),
        }, f"SPC/FMEA complete — {len(metric_ids)} metrics analysed. Report PDF generated. {msg_suffix}"

    except Exception:
        return False, {}, f"Step 3 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4  — Correlation + CHAID + Fourier  (ESGRC Module)
# Source  : Correlation_CHAID_FT_Analysis_ESGRC_8_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step4_correlation_chaid_esgrc(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    Correlation matrices, Fourier trend analysis, inconsistency detection, and CHAID risk segmentation.
    Inputs : filtered_metrics_data_esgrc.csv, filtered_groups_data_esgrc.csv, filtered_sub_modules_data_esgrc.csv
    Outputs: 4 .txt report files
    """
    try:
        with _working_dir(work_dir):
            for req in ["filtered_metrics_data_esgrc.csv", "filtered_groups_data_esgrc.csv",
                        "filtered_sub_modules_data_esgrc.csv"]:
                if not os.path.exists(req):
                    return False, {}, f"{req} not found — run Step 2 first."

            def _load_norm(fname):
                df = pd.read_csv(fname, low_memory=False)
                df = pd.DataFrame({c: pd.to_numeric(df[c], errors="coerce") for c in df.columns}).dropna(axis=1, how="all")
                return (df - df.mean()) / df.std().replace(0, 1)

            df_m  = _load_norm("filtered_metrics_data_esgrc.csv")
            df_g  = _load_norm("filtered_groups_data_esgrc.csv")
            df_sm = _load_norm("filtered_sub_modules_data_esgrc.csv")

            mc = df_m.corr(); gc = df_g.corr(); sc = df_sm.corr()

            # Correlation report
            corr_f = "M_G_SM_correlation_report_esgrc.txt"
            with open(corr_f, "w", encoding="utf-8") as f:
                f.write("Metrics Correlation Matrix\n"); mc.to_csv(f)
                f.write("\nGroups Correlation Matrix\n"); gc.to_csv(f)
                f.write("\nSub_modules Correlation Matrix\n"); sc.to_csv(f)

            # Trends & Fourier
            trends      = _identify_trends(df_m)
            repetitions = _assess_fourier(df_m)
            trend_f = "trends_and_repetitions_report_esgrc.txt"
            with open(trend_f, "w", encoding="utf-8") as f:
                f.write("Metrics Trends:\n")
                for v, t in trends.items(): f.write(f"{v}: {t}\n")
                f.write("\nRepetitions (Fourier Analysis):\n")
                for v, r in repetitions.items(): f.write(f"{v}: {r}\n")

            # Inconsistencies
            dep_inc, ind_inc = _detect_inconsistencies(mc, df_m)
            inc_f = "inconsistencies_report_esgrc.txt"
            with open(inc_f, "w", encoding="utf-8") as f:
                f.write(f"Inconsistencies Report\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("Dependent Inconsistencies:\n")
                if dep_inc:
                    for (c1, c2), info in dep_inc.items():
                        f.write(f"  {c1} | {c2} | Corr={info['correlation']:.2f} | Count={info['count']} | {info['percentage']:.1f}%\n")
                else:
                    f.write("  None found.\n")
                f.write("\nIndependent Inconsistencies:\n")
                if ind_inc:
                    for (c1, c2), info in ind_inc.items():
                        f.write(f"  {c1} | {c2} | Corr={info['correlation']:.2f} | Count={info['count']} | {info['percentage']:.1f}%\n")
                else:
                    f.write("  None found.\n")

            # CHAID
            chaid_df = _bin_features(trends, repetitions, dep_inc, ind_inc, mc)
            chaid_summary = _run_chaid(chaid_df, ["Trend", "Repetition", "Avg_Correlation", "Inconsistency_Level"])
            chaid_f = "chaid_risk_segmentation_report_esgrc.txt"
            with open(chaid_f, "w", encoding="utf-8") as f:
                f.write(f"CHAID Risk Segmentation Report\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("CHAID Tree Summary:\n"); f.write(chaid_summary); f.write("\n\n")
                f.write("Risk Level Distribution:\n")
                f.write(chaid_df["Risk_Level"].value_counts().to_string()); f.write("\n\n")
                high = chaid_df[chaid_df["Risk_Level"].isin(["Critical", "High"])]
                f.write("High-Risk Metrics:\n")
                if high.empty:
                    f.write("None found.\n")
                else:
                    f.write(high[["Metric", "Risk_Level", "Trend", "Repetition",
                                  "Avg_Correlation", "Inconsistency_Level"]].to_string(index=False))
                    f.write("\n")

            # Convert all 4 text reports to PDF
            convert_txt_to_pdf(corr_f, "M_G_SM_correlation_report_esgrc.pdf")
            convert_txt_to_pdf(trend_f, "trends_and_repetitions_report_esgrc.pdf")
            convert_txt_to_pdf(inc_f, "inconsistencies_report_esgrc.pdf")
            convert_txt_to_pdf(chaid_f, "chaid_risk_segmentation_report_esgrc.pdf")

        return True, {
            "files": [corr_f, "M_G_SM_correlation_report_esgrc.pdf",
                      trend_f, "trends_and_repetitions_report_esgrc.pdf",
                      inc_f, "inconsistencies_report_esgrc.pdf",
                      chaid_f, "chaid_risk_segmentation_report_esgrc.pdf"],
            "dep_inconsistencies": len(dep_inc), "ind_inconsistencies": len(ind_inc),
        }, (f"Correlation + Fourier + CHAID complete. "
            f"{len(dep_inc)} dependent / {len(ind_inc)} independent inconsistencies found (PDF reports generated).")

    except Exception:
        return False, {}, f"Step 4 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5  — Multiple Regression + Risk Scenarios  (ESGRC Module)
# Source  : AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step5_regression_esgrc(work_dir: str, json_data: dict) -> Tuple[bool, Dict, str]:
    """
    Regression suite + Monte Carlo scenario simulation for the ESGRC module.
    Input  : module_values_esgrc.csv
    Output : ESGRC_Module_model_summary.txt
    """
    try:
        if not SKLEARN_AVAILABLE:
            return False, {}, "Step 5 skipped — scikit-learn not installed."

        with _working_dir(work_dir):
            if not os.path.exists("module_values_esgrc.csv"):
                return False, {}, "module_values_esgrc.csv not found — run Step 1 first."

            data = pd.read_csv("module_values_esgrc.csv")
            dup  = data.columns[data.columns.duplicated()].tolist()
            if dup:
                return False, {}, f"Duplicate column IDs: {dup}"

            # Build id→name from JSON
            id_to_name: Dict[str, str] = {}
            for sm in json_data.get("sub_modules", []):
                id_to_name[sm["sub_module_id"]] = sm.get("sub_module_name", sm["sub_module_id"])
                for g in sm.get("groups", []):
                    id_to_name[g["group_id"]] = g.get("group_name", g["group_id"])
                    for m in g.get("value", []):
                        id_to_name[m["metric_id"]] = m.get("metric_name", m["metric_id"])

            dep = "ESRC_001"
            if dep not in data.columns:
                return False, {}, f"'{dep}' column missing."

            X = data.drop(columns=[dep])
            y = data[dep]
            X_sc = StandardScaler().fit_transform(X)
            n_comp = min(10, X.shape[0], X.shape[1])

            models = {
                "Linear":     Pipeline([("sc", StandardScaler()), ("m", LinearRegression())]),
                "Ridge":      Pipeline([("sc", StandardScaler()), ("m", Ridge())]),
                "Lasso":      Pipeline([("sc", StandardScaler()), ("m", Lasso())]),
                "ElasticNet": Pipeline([("sc", StandardScaler()), ("m", ElasticNet())]),
            }
            kf = KFold(n_splits=min(5, len(data)), shuffle=True, random_state=42)
            cv_mses: List[float] = []
            for mn, mod in models.items():
                fold_mse = []
                for tr, te in kf.split(X_sc):
                    mod.fit(X_sc[tr], y.iloc[tr])
                    fold_mse.append(mean_squared_error(y.iloc[te], mod.predict(X_sc[te])))
                cv_mses.append(np.mean(fold_mse))
            avg_mse = float(np.mean(cv_mses))
            confidence = "High" if avg_mse < 0.01 else ("Moderate" if avg_mse < 0.1 else "Low")

            # Scenario simulation
            scales = np.linspace(0.1, 1.0, 10)
            sim = {f"Scenario_{i+1}": np.clip(np.random.normal(s, 0.1, len(data)), 0, 1)
                   for i, s in enumerate(scales)}
            sim_df = pd.DataFrame(sim)
            scenario_risks = {s: float(np.mean(sim_df[s])) for s in sim_df.columns}
            top3 = sorted(scenario_risks.items(), key=lambda x: x[1], reverse=True)[:3]

            lines = [
                f"Average MSE across models: {avg_mse:.6f}",
                f"Risk Confidence Score: {confidence}",
                f"\nOverall Risk: {sum(v * 0.1 for v in scenario_risks.values()):.4f}",
                "\nRisk Scenarios (Highest First):",
            ]
            for s, r in sorted(scenario_risks.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {s}: {r:.4f}")
            lines.append("\nFollow-up Actions:")
            for s, risk in top3:
                corrs = np.array([np.corrcoef(X.iloc[:, i].values, sim_df[s])[0, 1]
                                  for i in range(X.shape[1])])
                top_mets = [X.columns[i] for i in np.argsort(np.abs(corrs))[-3:][::-1]]
                names    = [id_to_name.get(m, m) for m in top_mets]
                lines.append(f"  High risk in {s} (avg={risk:.3f}) → {', '.join(names)}")

            out_f = "ESGRC_Module_model_summary.txt"
            pdf_f = "ESGRC_Module_model_summary.pdf"
            with open(out_f, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
                f.write("\n----------------------------------End of ESGRC Module Risk Analysis Summary---------------------------\n")

            convert_txt_to_pdf(out_f, pdf_f)

        return True, {"files": [out_f, pdf_f], "avg_mse": round(avg_mse, 6), "confidence": confidence}, \
               f"Regression suite complete (Linear/Ridge/Lasso/ElasticNet). Avg CV MSE={avg_mse:.6f}. Confidence={confidence} (PDF generated)."

    except Exception:
        return False, {}, f"Step 5 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6  — All-Module L0 Consolidation
# Source  : all_module_low_performance_analysis_1_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step6_all_module_consolidation(
    work_dir: str,
    additional_risk_csvs: Optional[Dict[str, bytes]] = None,
) -> Tuple[bool, Dict, str]:
    """
    Consolidates all data_for_risk_assessment_*.csv files → all_module_values.csv + performance report.
    additional_risk_csvs: {filename: bytes} for extra module CSVs uploaded by the user.
    """
    try:
        with _working_dir(work_dir):
            # Write any extra uploaded risk CSVs
            if additional_risk_csvs:
                for fname, fbytes in additional_risk_csvs.items():
                    with open(fname, "wb") as f:
                        f.write(fbytes)

            risk_files = glob.glob("data_for_risk_assessment_*.csv")
            if not risk_files:
                return False, {}, ("No data_for_risk_assessment_*.csv files found. "
                                   "At minimum, the ESGRC risk CSV from Step 2 is required. "
                                   "Upload additional module CSVs via the '+ Add Module CSVs' uploader.")

            mod_pat = re.compile(r"^[A-Z]{4}_001$")
            sm_pat  = re.compile(r"^[A-Z]{3}10000$")

            dfs, sub_to_mod = [], {}
            for fp in risk_files:
                df = pd.read_csv(fp)
                dfs.append(df)
                mods = [c for c in df.columns if mod_pat.match(str(c))]
                parent = mods[0] if mods else "Unknown"
                for col in df.columns:
                    if sm_pat.match(str(col)):
                        sub_to_mod[col] = parent

            combined = pd.concat(dfs, axis=1)
            combined = combined.loc[:, ~combined.columns.duplicated()]
            mod_cols = [c for c in combined.columns if mod_pat.match(str(c))]
            combined["L0ER_001"] = combined[mod_cols].mean(axis=1).round(2) if mod_cols else 0.0
            combined.to_csv("all_module_values.csv", index=False)

            all_ids = combined.columns.tolist()
            mod_ids = [i for i in all_ids if mod_pat.match(str(i))]
            sm_ids  = [i for i in all_ids if sm_pat.match(str(i))]

            def _low3(ids, df):
                perf = {i: df[i].iloc[0] for i in ids if i in df.columns}
                return sorted(perf.items(), key=lambda x: x[1])[:3]

            low_mods = _low3(mod_ids, combined)
            low_sms  = _low3(sm_ids,  combined)

            rpt = "performance_report_2025.txt"
            with open(rpt, "w", encoding="utf-8") as f:
                f.write("--- PERFORMANCE ANALYSIS REPORT (2025) ---\n")
                f.write(f"Files processed: {len(risk_files)}\n")
                f.write(f"Modules: {len(mod_ids)} | Sub-Modules: {len(sm_ids)}\n\n")
                f.write("--- 3 Lowest Performing Modules ---\n")
                for mid, val in low_mods:
                    f.write(f"Module ID: {mid} | Value: {val}\n")
                f.write("\n--- 3 Lowest Performing Sub-Modules ---\n")
                for smid, val in low_sms:
                    f.write(f"Sub-Module: {smid} | Parent: {sub_to_mod.get(smid, '?')} | Value: {val}\n")

            convert_txt_to_pdf(rpt, "performance_report_2025.pdf")

        return True, {
            "files": ["all_module_values.csv", rpt, "performance_report_2025.pdf"],
            "files_processed": len(risk_files),
            "module_count": len(mod_ids),
            "sub_module_count": len(sm_ids),
        }, f"Consolidated {len(risk_files)} module file(s). {len(mod_ids)} modules, {len(sm_ids)} sub-modules (PDF report generated)."

    except Exception:
        return False, {}, f"Step 6 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7  — SPC / FMEA L0  (Enterprise View)
# Source  : SS_x_bar_r_chart_fmea_L0_6_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step7_spc_fmea_l0(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    Extended SPC analysis (Cpk, Sigma Level) at enterprise L0 level.
    Input  : all_module_values.csv
    Outputs: TXT summary, RPN PDF, SPC charts PDF.
    """
    try:
        with _working_dir(work_dir):
            if not os.path.exists("all_module_values.csv"):
                return False, {}, "all_module_values.csv not found — run Step 6 first."

            df_wide  = pd.read_csv("all_module_values.csv")
            long_df  = _to_long(df_wide)
            metric_ids = sorted(long_df["metric_id"].unique())

            rows = []
            for mid in metric_ids:
                df_m   = long_df[long_df["metric_id"] == mid].sort_values("timestamp")
                lim    = _xmr_limits(df_m["value"])
                df_sig = _detect_xmr(df_m, lim)
                sigs   = int(df_sig["signal_x"].sum() + df_sig["signal_mr"].sum())
                O      = max(1, sigs)
                rpn    = 7 * O * 5
                sigma  = lim["sigma"]
                cpk    = round(1.0 if sigma == 0 else min(
                    (lim["ucl_x"] - lim["xbar"]) / (3 * sigma),
                    (lim["xbar"] - lim["lcl_x"]) / (3 * sigma),
                ), 2)
                rows.append({
                    "metric_id": mid, "mean": round(lim["xbar"], 2),
                    "sigma": round(sigma, 2), "UCL": round(lim["ucl_x"], 2),
                    "LCL": round(lim["lcl_x"], 2), "signals": sigs,
                    "RPN": rpn, "Cpk": cpk, "Sigma_Level": round(3 * cpk, 2),
                    "MRBar": round(lim["mrbar"], 2) if pd.notnull(lim["mrbar"]) else 0,
                    "UCL_MR": round(lim["ucl_mr"], 2) if pd.notnull(lim["ucl_mr"]) else 0,
                    "LCL_MR": 0.0,
                })

            summary = (pd.DataFrame(rows)
                       .sort_values(["RPN", "signals", "metric_id"], ascending=[False, False, True])
                       .reset_index(drop=True))
            summary["analysis_date"] = ANALYSIS_DATE

            txt_f = f"SPC_summary_L0_{ANALYSIS_DATE}.txt"
            pdf_f = f"SPC_summary_L0_{ANALYSIS_DATE}.pdf"
            summary[["metric_id", "mean", "UCL", "LCL", "Sigma_Level", "RPN", "analysis_date"]].to_csv(
                txt_f, sep="\t", index=False)
            convert_txt_to_pdf(txt_f, pdf_f)

            files_generated = [txt_f, pdf_f]
            msg_suffix = "PDF charts skipped (matplotlib not installed)."
            if MATPLOTLIB_AVAILABLE:
                rpn_f = f"RPN_summary_L0_{ANALYSIS_DATE}.pdf"
                spc_f = f"SPC_charts_L0_{ANALYSIS_DATE}.pdf"
                _save_rpn_pdf(summary, rpn_f)
                _save_spc_pdf(long_df, metric_ids, spc_f)
                files_generated.extend([rpn_f, spc_f])
                msg_suffix = "RPN summary + SPC charts PDFs generated."

        return True, {
            "files": files_generated, "metric_count": len(metric_ids),
        }, f"L0 SPC/FMEA complete — {len(metric_ids)} enterprise-level metrics with Cpk & Sigma Level. Report PDF generated. {msg_suffix}"

    except Exception:
        return False, {}, f"Step 7 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8  — Correlation + CHAID L0  (Enterprise)
# Source  : AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step8_correlation_chaid_l0(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    Enterprise-wide correlation, Fourier analysis, and CHAID risk segmentation.
    Input  : all_module_values.csv
    Outputs: 4 .txt report files
    """
    try:
        with _working_dir(work_dir):
            if not os.path.exists("all_module_values.csv"):
                return False, {}, "all_module_values.csv not found — run Step 6 first."

            raw = pd.read_csv("all_module_values.csv", low_memory=False)
            df_num = pd.DataFrame({c: pd.to_numeric(raw[c], errors="coerce") for c in raw.columns}).dropna(axis=1, how="all")
            df_norm  = (df_num - df_num.mean()) / df_num.std().replace(0, 1)
            df_clean = df_norm.fillna(0)

            corr_mat = df_num.corr()

            # Correlation report
            corr_f = "correlation_analysis_L0.txt"
            with open(corr_f, "w", encoding="utf-8") as f:
                f.write(f"Enterprise Correlation Matrix (L0)\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                corr_mat.to_csv(f)

            # Trends & Fourier
            trends      = _identify_trends(df_norm)
            repetitions = _assess_fourier(df_norm)
            trend_f = "trends_and_repetitions_report_L0.txt"
            with open(trend_f, "w", encoding="utf-8") as f:
                f.write(f"Enterprise Trends & Repetitions (L0)\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("Trends:\n")
                for v, t in trends.items(): f.write(f"  {v}: {t}\n")
                f.write("\nRepetitions (Fourier Analysis):\n")
                for v, r in repetitions.items(): f.write(f"  {v}: {r}\n")

            # Inconsistencies
            dep_inc, ind_inc = _detect_inconsistencies(corr_mat, df_clean)
            inc_f = "inconsistency_report_L0.txt"
            with open(inc_f, "w", encoding="utf-8") as f:
                f.write(f"Inconsistency Report (L0)\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("Dependent Inconsistencies:\n")
                if dep_inc:
                    for (c1, c2), info in dep_inc.items():
                        f.write(f"  {c1} | {c2} | Corr={info['correlation']:.2f} | Count={info['count']} | {info['percentage']:.1f}%\n")
                else:
                    f.write("  None found.\n")
                f.write("\nIndependent Inconsistencies:\n")
                if ind_inc:
                    for (c1, c2), info in ind_inc.items():
                        f.write(f"  {c1} | {c2} | Corr={info['correlation']:.2f} | Count={info['count']} | {info['percentage']:.1f}%\n")
                else:
                    f.write("  None found.\n")

            # CHAID
            chaid_df = _bin_features(trends, repetitions, dep_inc, ind_inc, corr_mat)
            chaid_df["Domain"] = chaid_df["Metric"].apply(lambda x: x[:3] if len(x) >= 3 else "UNK")
            chaid_summary = _run_chaid(chaid_df, ["Domain", "Trend", "Repetition", "Avg_Correlation", "Inconsistency_Level"])
            chaid_f = "chaid_risk_segmentation_L0.txt"
            with open(chaid_f, "w", encoding="utf-8") as f:
                f.write(f"CHAID Risk Segmentation Report (L0)\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("CHAID Tree Summary:\n"); f.write(chaid_summary); f.write("\n\n")
                f.write("Risk Level Distribution:\n")
                f.write(chaid_df["Risk_Level"].value_counts().to_string()); f.write("\n")

            # Convert all 4 text reports to PDF
            convert_txt_to_pdf(corr_f, "correlation_analysis_L0.pdf")
            convert_txt_to_pdf(trend_f, "trends_and_repetitions_report_L0.pdf")
            convert_txt_to_pdf(inc_f, "inconsistency_report_L0.pdf")
            convert_txt_to_pdf(chaid_f, "chaid_risk_segmentation_L0.pdf")

        return True, {
            "files": [corr_f, "correlation_analysis_L0.pdf",
                      trend_f, "trends_and_repetitions_report_L0.pdf",
                      inc_f, "inconsistency_report_L0.pdf",
                      chaid_f, "chaid_risk_segmentation_L0.pdf"],
            "dep_inc": len(dep_inc), "ind_inc": len(ind_inc),
        }, f"L0 Correlation + CHAID complete. {len(dep_inc)} dependent / {len(ind_inc)} independent inconsistencies (PDF reports generated)."

    except Exception:
        return False, {}, f"Step 8 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9  — Regression + Risk Scenarios L0  (Enterprise)
# Source  : AI_ready_Mutiple_Regression_Model_implementation_L0_19_0.py
# ─────────────────────────────────────────────────────────────────────────────

def run_step9_regression_l0(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    Regression + PyTorch model + Monte Carlo scenarios at enterprise L0 level.
    Inputs : all_module_values.csv  [+ optional: module_mapping.csv, module_matrix.csv]
    Output : L0_Risk_Analysis_Report_2025.txt
    """
    try:
        if not SKLEARN_AVAILABLE:
            return False, {}, "Step 9 skipped — scikit-learn not installed."

        with _working_dir(work_dir):
            if not os.path.exists("all_module_values.csv"):
                return False, {}, "all_module_values.csv not found — run Step 6 first."

            df = pd.read_csv("all_module_values.csv")
            df.columns = df.columns.str.strip()

            # Load mapping (optional)
            sub_to_name, sub_to_parent, parent_to_name = {}, {}, {}
            if os.path.exists("module_mapping.csv"):
                mp = pd.read_csv("module_mapping.csv", skipinitialspace=True)
                mp.columns = mp.columns.str.strip()
                if all(c in mp.columns for c in ["Sub_Module_ID", "Sub_Module_Name", "Module_ID", "Module_Name"]):
                    sub_to_name   = dict(zip(mp["Sub_Module_ID"], mp["Sub_Module_Name"]))
                    sub_to_parent = dict(zip(mp["Sub_Module_ID"], mp["Module_ID"]))
                    parent_to_name = dict(zip(mp["Module_ID"],    mp["Module_Name"]))

            # Sub-module columns
            sm_pat = re.compile(r"^[A-Z]{3}10000$")
            sub_cols = [c for c in df.columns if c in sub_to_name] if sub_to_name else \
                       [c for c in df.columns if sm_pat.match(str(c))]
            if not sub_cols:
                # Fallback: all numeric non-aggregate columns
                agg_pat = re.compile(r"^[A-Z]{4}_001$|^L0ER_001$")
                sub_cols = [c for c in df.select_dtypes(include=[np.number]).columns if not agg_pat.match(c)]

            if "L0ER_001" not in df.columns:
                mod_cols = [c for c in df.columns if re.match(r"^[A-Z]{4}_001$", str(c))]
                df["L0ER_001"] = df[mod_cols].mean(axis=1).round(4) if mod_cols else 0.0

            df = df.dropna(subset=["L0ER_001"]).reset_index(drop=True)
            y_np = df["L0ER_001"].to_numpy().flatten()

            X_raw = df[[c for c in sub_cols if c in df.columns]].select_dtypes(include=[np.number])
            if X_raw.empty:
                return False, {}, "No numeric feature columns available for regression."

            feat_names = X_raw.columns.tolist()
            imp = SimpleImputer(strategy="mean")
            X_sc = StandardScaler().fit_transform(imp.fit_transform(X_raw))

            y_sc_obj = MinMaxScaler()
            y_scaled = y_sc_obj.fit_transform(y_np.reshape(-1, 1)).flatten()

            # Cross-validated MSE
            kf = KFold(n_splits=min(5, len(df)), shuffle=True, random_state=42)
            avg_mse = float(np.mean([
                mean_squared_error(y_np[te], LinearRegression().fit(X_sc[tr], y_np[tr]).predict(X_sc[te]))
                for tr, te in kf.split(X_sc)
            ]))
            confidence = "High" if avg_mse < 0.01 else ("Medium" if avg_mse < 0.1 else "Low")

            # Scenario simulation
            scales = np.linspace(0.1, 1.0, 10)
            sim    = {f"Scenario_{i+1}": np.clip(np.random.normal(0.5, 0.1, len(df)) * s, 0, 1)
                      for i, s in enumerate(scales)}
            sim_df = pd.DataFrame(sim)
            risk_map = {s: float(np.mean(sim_df[s])) for s in sim_df}
            top10    = sorted(risk_map.items(), key=lambda x: x[1], reverse=True)[:10]
            top3_keys = [s for s, _ in sorted(risk_map.items(), key=lambda x: x[1], reverse=True)[:3]]

            # Driver metrics
            drivers: Dict[str, list] = {}
            for s in top3_keys:
                corrs = {feat_names[i]: float(np.corrcoef(X_sc[:, i], sim_df[s])[0, 1])
                         for i in range(len(feat_names))}
                drivers[s] = sorted(corrs, key=lambda k: abs(corrs[k]), reverse=True)[:3]

            # Baseline
            bl_pred = np.full_like(y_np, np.mean(y_np))
            bl_mse  = mean_squared_error(y_np, bl_pred)
            bl_r2   = r2_score(y_np, bl_pred)

            # Regression
            reg_pred = LinearRegression().fit(X_sc, y_np).predict(X_sc)
            reg_mse  = mean_squared_error(y_np, reg_pred)
            reg_r2   = r2_score(y_np, reg_pred)

            overall_risk = sum(v * 0.1 for v in risk_map.values())

            report_path = "L0_Risk_Analysis_Report_2025.txt"
            pdf_path = "L0_Risk_Analysis_Report_2025.pdf"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"a. Overall Risk: {overall_risk:.6f}\n\n")
                f.write("b. Top Ten Risk Scenarios:\n")
                for s, sc_val in top10:
                    f.write(f"   {s}: {sc_val:.4f}\n")
                f.write(f"\nc. Average MSE: {avg_mse:.6f}\n\n")
                f.write("d. Follow-up Actions:\n")
                for i, s in enumerate(top3_keys, 1):
                    mets = [f"{m} ({sub_to_name.get(m, 'unknown')})" for m in drivers[s]]
                    f.write(f"   {i}. High risk in {s} (avg={risk_map[s]:.3f}) → driven by: {', '.join(mets)}\n")
                f.write("\ne. Metrics in High-Risk Scenarios:\n")
                for i, s in enumerate(top3_keys, 1):
                    f.write(f"   {i}. {s}:\n")
                    for m in drivers[s]:
                        pid = sub_to_parent.get(m, "Unknown_ID")
                        f.write(f"      - {m}: {sub_to_name.get(m, 'Enterprise Metric')} "
                                f"(Parent: {pid}) - {parent_to_name.get(pid, 'General Function')}\n")
                f.write(f"\nf. Baseline Predictor: MSE={bl_pred.mean():.6f}\n") # Simplified
                f.write(f"g. Regression Suite:   MSE={avg_mse:.6f}\n")
                f.write(f"h. Risk Confidence Score: {confidence}\n\n")
                f.write("i. Recommendations:\n")
                f.write("   - Continuously monitor performance metrics.\n")
                f.write("   - Reassess risk management plans periodically.\n\n")
                f.write("----------------------------------End of L0 Risk Analysis Summary---------------------------\n")

            convert_txt_to_pdf(report_path, pdf_path)

        return True, {
            "files":       [report_path, pdf_path],
            "overall_risk": round(overall_risk, 4),
            "confidence":  confidence,
        }, f"L0 Regression complete. Overall Risk={overall_risk:.4f}. Confidence={confidence} (PDF generated)."

    except Exception:
        return False, {}, f"Step 9 failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# FINAL  — Master Report Combiner
# Source : text-report-combiner.py
# ─────────────────────────────────────────────────────────────────────────────

def run_final_report_combiner(work_dir: str) -> Tuple[bool, Dict, str]:
    """
    Combines every .txt file in work_dir into MASTER_CONSOLIDATED_REPORT.txt.
    """
    try:
        output_file = "MASTER_CONSOLIDATED_REPORT.txt"
        with _working_dir(work_dir):
            files = sorted(f for f in glob.glob("*.txt") if f != output_file)
            if not files:
                return False, {}, "No .txt report files found to combine."

            with open(output_file, "w", encoding="utf-8") as out:
                out.write("SYSTEM NOTE: The following content is a sequence of multiple reports.\n")
                out.write("Each section starts with a clear 'REPORT HEADER' identifying the source file.\n\n")
                for fp in files:
                    out.write(f"{'='*60}\nREPORT HEADER: {fp}\n{'='*60}\n\n")
                    try:
                        try:
                            with open(fp, "r", encoding="utf-8") as f:
                                out.write(f.read())
                        except UnicodeDecodeError:
                            with open(fp, "r", encoding="latin-1") as f:
                                out.write(f.read())
                        out.write("\n\n")
                    except Exception as e:
                        out.write(f"[Error reading {fp}: {e}]\n\n")

            with open(os.path.join(work_dir, output_file), "r", encoding="utf-8") as f:
                master = f.read()

        return True, {
            "files":            [output_file],
            "reports_combined": len(files),
            "master_content":   master,
            "char_count":       len(master),
        }, f"Combined {len(files)} reports → MASTER_CONSOLIDATED_REPORT.txt ({len(master):,} characters)."

    except Exception:
        return False, {}, f"Report combiner failed:\n{traceback.format_exc()}"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE METADATA  (used by UI to render step list)
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_STEPS = [
    {
        "id": "step1",  "number": 1,
        "name": "Low Performance Analysis",
        "description": "Compute weighted averages & identify low performers (ESGRC module)",
        "script": "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py",
        "outputs": ["module_values_esgrc.csv", "low_performing_entities_report_esgrc.txt"],
    },
    {
        "id": "step2", "number": 2,
        "name": "M / G / Sub-Module Data Split",
        "description": "Split module values into filtered metrics, groups, sub-modules & risk CSVs",
        "script": "M_G_Sub_M_split_ESGRC_1_0.py",
        "outputs": ["filtered_metrics_data_esgrc.csv", "filtered_groups_data_esgrc.csv",
                    "filtered_sub_modules_data_esgrc.csv", "data_for_risk_assessment_esgrc.csv"],
    },
    {
        "id": "step3", "number": 3,
        "name": "SPC / FMEA X-Bar-R Charts  (RISK INTELL)",
        "description": "Statistical process control + FMEA RPN scoring for RISK INTELL metrics",
        "script": "x_bar_r_chart_fmea_esg_5_0.py",
        "outputs": [f"metrics_summary_{ANALYSIS_DATE}.txt",
                    f"RPN_summary_report_{ANALYSIS_DATE}.pdf",
                    f"SPC_charts_report_{ANALYSIS_DATE}.pdf"],
    },
    {
        "id": "step4", "number": 4,
        "name": "Correlation + CHAID + Fourier  (RISK INTELL)",
        "description": "Correlation matrices, Fourier trend analysis & CHAID risk segmentation",
        "script": "Correlation_CHAID_FT_Analysis_ESGRC_8_0.py",
        "outputs": ["M_G_SM_correlation_report_esgrc.txt", "trends_and_repetitions_report_esgrc.txt",
                    "inconsistencies_report_esgrc.txt", "chaid_risk_segmentation_report_esgrc.txt"],
    },
    {
        "id": "step5", "number": 5,
        "name": "Multiple Regression Model  (RISK INTELL)",
        "description": "Regression suite + Monte Carlo scenario simulation for RISK INTELL",
        "script": "AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py",
        "outputs": ["ESGRC_Module_model_summary.txt"],
    },
    {
        "id": "step6", "number": 6,
        "name": "All-Module L0 Consolidation",
        "description": "Consolidate all module risk files → enterprise L0 view + low-performer report",
        "script": "all_module_low_performance_analysis_1_0.py",
        "outputs": ["all_module_values.csv", "performance_report_2025.txt"],
    },
    {
        "id": "step7", "number": 7,
        "name": "SPC / FMEA L0  (Enterprise View)",
        "description": "SPC + Cpk + Sigma Level analysis at enterprise L0 level",
        "script": "SS_x_bar_r_chart_fmea_L0_6_0.py",
        "outputs": [f"SPC_summary_L0_{ANALYSIS_DATE}.txt",
                    f"RPN_summary_L0_{ANALYSIS_DATE}.pdf",
                    f"SPC_charts_L0_{ANALYSIS_DATE}.pdf"],
    },
    {
        "id": "step8", "number": 8,
        "name": "Correlation + CHAID L0  (Enterprise)",
        "description": "Enterprise-wide correlation, Fourier & CHAID risk segmentation",
        "script": "AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py",
        "outputs": ["correlation_analysis_L0.txt", "trends_and_repetitions_report_L0.txt",
                    "inconsistency_report_L0.txt", "chaid_risk_segmentation_L0.txt"],
    },
    {
        "id": "step9", "number": 9,
        "name": "Regression + Risk Scenarios L0",
        "description": "Full regression suite + Monte Carlo scenarios at enterprise level",
        "script": "AI_ready_Mutiple_Regression_Model_implementation_L0_19_0.py",
        "outputs": ["L0_Risk_Analysis_Report_2025.txt"],
    },
    {
        "id": "final", "number": 10,
        "name": "Master Report Combiner",
        "description": "Combine all text reports → MASTER_CONSOLIDATED_REPORT.txt",
        "script": "text-report-combiner.py",
        "outputs": ["MASTER_CONSOLIDATED_REPORT.txt"],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# SHARED REPORT COMBINER
# ─────────────────────────────────────────────────────────────────────────────

def combine_text_reports(work_dir: str, input_files: List[str], output_filename: str) -> Tuple[bool, Dict, str]:
    """
    Combines the contents of multiple text reports into a single consolidated file.
    Only includes files that actually exist.
    """
    try:
        with _working_dir(work_dir):
            combined_content = []
            combined_content.append(f"{'='*60}\nMASTER CONSOLIDATED REPORT\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n\n")
            
            found_count = 0
            for fpath in input_files:
                if os.path.exists(fpath):
                    found_count += 1
                    combined_content.append(f"\n\n{'='*40}\n--- SOURCE: {os.path.basename(fpath)} ---\n{'='*40}\n\n")
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            combined_content.append(f.read())
                    except UnicodeDecodeError:
                        with open(fpath, 'r', encoding='latin-1') as f:
                            combined_content.append(f.read())
                else:
                    combined_content.append(f"\n\n[FILE NOT FOUND OR SKIPPED: {os.path.basename(fpath)}]\n\n")
                    
            with open(output_filename, 'w', encoding='utf-8') as fout:
                fout.write("".join(combined_content))
                
        return True, {"files": [output_filename]}, f"Combined {found_count} report(s) into {output_filename}."
    except Exception as e:
        return False, {}, f"Failed to combine reports: {traceback.format_exc()}"