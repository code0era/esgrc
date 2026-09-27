import streamlit as st
import os
import json
import tempfile
import pandas as pd
import utils.pipeline_engine as pe
from utils.pipeline_ui import init_pipeline_state, render_pipeline_step

def generate_ai_pdf(text, title):
    """Convert AI-generated markdown text to a fully-styled, non-truncating PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    import io, re

    PAGE_W, PAGE_H = A4
    MARGIN = 1.8 * cm

    # ── Colour tokens ───────────────────────────────────────────────────
    SKY_DARK  = HexColor("#0284C7")
    SKY_MID   = HexColor("#0EA5E9")
    SKY_LIGHT = HexColor("#BAE6FD")
    SKY_PALE  = HexColor("#F0F9FF")
    INK_DARK  = HexColor("#0C4A6E")
    INK_GRAY  = HexColor("#475569")
    RED_CLR   = HexColor("#EF4444")
    AMBER_CLR = HexColor("#F59E0B")
    GREEN_CLR = HexColor("#10B981")

    # ── Styles ──────────────────────────────────────────────────────────
    title_style = ParagraphStyle("AITitle",    fontName="Helvetica-Bold",   fontSize=20, textColor=INK_DARK,  spaceAfter=10, leading=26)
    h1_style    = ParagraphStyle("AIH1",       fontName="Helvetica-Bold",   fontSize=14, textColor=INK_DARK,  spaceBefore=18, spaceAfter=8,  leading=20)
    h2_style    = ParagraphStyle("AIH2",       fontName="Helvetica-Bold",   fontSize=12, textColor=SKY_DARK,  spaceBefore=14, spaceAfter=6,  leading=16)
    h3_style    = ParagraphStyle("AIH3",       fontName="Helvetica-BoldOblique", fontSize=10.5, textColor=HexColor("#0369A1"), spaceBefore=10, spaceAfter=4, leading=14)
    body_style  = ParagraphStyle("AIBody",     fontName="Helvetica",        fontSize=9.5, textColor=INK_DARK, spaceAfter=5,  leading=14)
    bullet_style= ParagraphStyle("AIBullet",   fontName="Helvetica",        fontSize=9.5, textColor=INK_DARK, spaceAfter=3,  leading=13, leftIndent=14, firstLineIndent=0)
    mono_style  = ParagraphStyle("AIMono",     fontName="Courier",          fontSize=8,   textColor=HexColor("#1E293B"), spaceAfter=3, leading=11, leftIndent=8)
    tbl_hdr_sty = ParagraphStyle("AITblHdr",   fontName="Helvetica-Bold",   fontSize=8.5, textColor=white, alignment=1)
    tbl_cel_sty = ParagraphStyle("AITblCell",  fontName="Helvetica",        fontSize=8.5, textColor=INK_DARK, leading=11)
    label_style = ParagraphStyle("AILabel",    fontName="Helvetica",        fontSize=8,   textColor=INK_GRAY)
    value_style = ParagraphStyle("AIValue",    fontName="Helvetica-Bold",   fontSize=9,   textColor=INK_DARK)

    # ── Header / Footer callbacks ────────────────────────────────────────
    def draw_header_footer(canvas, doc):
        canvas.saveState()
        # Header bar
        canvas.setFillColor(SKY_DARK)
        canvas.rect(0, PAGE_H - 2.2*cm, PAGE_W, 2.2*cm, fill=1, stroke=0)
        canvas.setFillColor(SKY_MID)
        canvas.rect(0, PAGE_H - 2.32*cm, PAGE_W, 0.12*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(white)
        canvas.drawString(MARGIN, PAGE_H - 1.1*cm, "🛡  METEOERAIT SOFTWARE")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(SKY_LIGHT)
        canvas.drawString(MARGIN, PAGE_H - 1.75*cm, "AI Enterprise Risk & Compliance Analysis Report  |  CONFIDENTIAL")
        # Footer bar
        canvas.setFillColor(SKY_PALE)
        canvas.rect(0, 0, PAGE_W, 1.3*cm, fill=1, stroke=0)
        canvas.setStrokeColor(SKY_LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(0, 1.3*cm, PAGE_W, 1.3*cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(INK_GRAY)
        canvas.drawString(MARGIN, 0.45*cm, "METEOERAIT SOFTWARE — Confidential & Proprietary")
        canvas.drawRightString(PAGE_W - MARGIN, 0.45*cm, f"Page {doc.page}")
        canvas.restoreState()

    def draw_cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(SKY_DARK)
        canvas.rect(0, 0, 1.8*cm, PAGE_H, fill=1, stroke=0)
        canvas.setFillColor(SKY_MID)
        canvas.rect(1.8*cm, 0, 0.22*cm, PAGE_H, fill=1, stroke=0)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK_GRAY)
        canvas.drawString(2.5*cm, 0.9*cm, "METEOERAIT SOFTWARE — Enterprise Intelligence AI Report")
        canvas.drawRightString(PAGE_W - MARGIN, 0.9*cm, "CONFIDENTIAL")
        canvas.restoreState()

    # ── Markdown table parser ────────────────────────────────────────────
    def parse_md_table(lines):
        """Parse markdown table lines into list-of-lists (str)."""
        rows = []
        for ln in lines:
            ln = ln.strip()
            if ln.startswith("|"):
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if all(re.match(r"^[-: ]+$", c) for c in cells):
                    continue  # separator row
                rows.append(cells)
        return rows

    def build_md_table(md_rows, usable_w):
        if not md_rows:
            return None
        n_cols = max(len(r) for r in md_rows)
        col_w = usable_w / n_cols

        header = md_rows[0]
        data_rows = md_rows[1:]

        tbl_data = [[Paragraph(str(c), tbl_hdr_sty) for c in header]]
        for row in data_rows:
            padded = list(row) + [""] * (n_cols - len(row))
            tbl_data.append([Paragraph(str(c), tbl_cel_sty) for c in padded])

        style_cmds = [
            ("BACKGROUND",  (0,0), (-1,0),  SKY_DARK),
            ("BACKGROUND",  (0,1), (-1,-1), SKY_PALE),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, SKY_PALE]),
            ("BOX",         (0,0), (-1,-1), 0.4, SKY_LIGHT),
            ("INNERGRID",   (0,0), (-1,-1), 0.3, SKY_LIGHT),
            ("PADDING",     (0,0), (-1,-1), 5),
            ("VALIGN",      (0,0), (-1,-1), "TOP"),
        ]
        t = Table(tbl_data, colWidths=[col_w]*n_cols, repeatRows=1)
        t.setStyle(TableStyle(style_cmds))
        return t

    # ── Build story ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    usable_w = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=3.0*cm, bottomMargin=1.8*cm,
        title=title, author="METEOERAIT SOFTWARE",
    )

    story = []

    # Cover page
    from datetime import datetime
    story.append(Spacer(1, 3.5*cm))
    story.append(Paragraph("METEOERAIT SOFTWARE", ParagraphStyle("CoverBrand", fontName="Helvetica-Bold", fontSize=26, textColor=INK_DARK, leftIndent=1.2*cm)))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(title, ParagraphStyle("CoverTitle", fontName="Helvetica", fontSize=15, textColor=INK_GRAY, leftIndent=1.2*cm, leading=20)))
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width=usable_w, thickness=2, color=SKY_MID, spaceAfter=14))

    meta = [
        [Paragraph("Generated:", label_style), Paragraph(datetime.now().strftime("%B %d, %Y  %H:%M"), value_style),
         Paragraph("Classification:", label_style), Paragraph("CONFIDENTIAL", value_style)],
        [Paragraph("Report Type:", label_style), Paragraph("AI Enterprise Risk Assessment", value_style),
         Paragraph("Engine:", label_style), Paragraph("Claude AI (Anthropic)", value_style)],
    ]
    mt = Table(meta, colWidths=[3*cm, 5*cm, 3*cm, 5.5*cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), SKY_PALE),
        ("BOX", (0,0), (-1,-1), 0.5, SKY_LIGHT),
        ("PADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(mt)
    story.append(PageBreak())

    # ── Parse the AI text into story elements ────────────────────────────
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Blank line
        if not stripped:
            story.append(Spacer(1, 0.15*cm))
            i += 1
            continue

        # Headings
        if stripped.startswith("#### "):
            story.append(Paragraph(stripped[5:].replace("**",""), h3_style))
            i += 1; continue
        if stripped.startswith("### "):
            story.append(Paragraph(stripped[4:].replace("**",""), h3_style))
            i += 1; continue
        if stripped.startswith("## "):
            story.append(HRFlowable(width=usable_w, thickness=1, color=SKY_LIGHT, spaceAfter=4))
            story.append(Paragraph(stripped[3:].replace("**",""), h2_style))
            i += 1; continue
        if stripped.startswith("# "):
            story.append(PageBreak())
            story.append(Paragraph(stripped[2:].replace("**",""), h1_style))
            story.append(HRFlowable(width=usable_w, thickness=1.5, color=SKY_MID, spaceAfter=6))
            i += 1; continue

        # Markdown table — collect all consecutive table lines
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            md_rows = parse_md_table(table_lines)
            tbl = build_md_table(md_rows, usable_w)
            if tbl:
                story.append(Spacer(1, 0.2*cm))
                story.append(tbl)
                story.append(Spacer(1, 0.3*cm))
            continue

        # Horizontal rule
        if stripped.startswith("---") and len(set(stripped)) == 1:
            story.append(HRFlowable(width=usable_w, thickness=0.5, color=SKY_LIGHT, spaceAfter=6))
            i += 1; continue

        # Bullet / list items
        if stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+\.\s", stripped):
            clean = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", stripped)
            clean = re.sub(r"_(.*?)_", r"<i>\1</i>", clean)
            clean = re.sub(r"`(.*?)`", r"<font face='Courier'>\1</font>", clean)
            prefix = "• " if not re.match(r"^\d+\.\s", stripped) else ""
            body = clean[2:] if (stripped.startswith("- ") or stripped.startswith("* ")) else clean
            try:
                story.append(Paragraph(prefix + body, bullet_style))
            except Exception:
                import html
                plain_body = stripped[2:] if (stripped.startswith("- ") or stripped.startswith("* ")) else stripped
                story.append(Paragraph(prefix + html.escape(plain_body), bullet_style))
            i += 1; continue

        # Normal paragraph — inline markup
        clean = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", stripped)
        clean = re.sub(r"_(.*?)_",       r"<i>\1</i>", clean)
        clean = re.sub(r"`(.*?)`",       r"<font face='Courier'>\1</font>", clean)
        try:
            story.append(Paragraph(clean, body_style))
        except Exception:
            import html
            story.append(Paragraph(html.escape(stripped), body_style))
        i += 1

    # ── Build doc ────────────────────────────────────────────────────────
    def _first_page(c, d):  draw_cover(c, d)
    def _later_pages(c, d): draw_header_footer(c, d)

    doc.build(story, onFirstPage=_first_page, onLaterPages=_later_pages)
    return buf.getvalue()


def generate_offline_report(content, is_apex=False):
    lines = content.split('\n')
    critical_risks = [line for line in lines if "Critical" in line or "High Risk" in line or "Anomaly" in line][:8]
    
    report = f"FINAL {'ENTERPRISE' if is_apex else 'CLIENT'} RECOMMENDED REPORT\n"
    report += "=" * 60 + "\n\n"
    report += "EXECUTIVE SUMMARY\n"
    report += "-----------------\n"
    report += "This report was generated securely offline. Based on the aggregated data across all modules, we have identified several key areas requiring immediate attention.\n\n"
    
    report += "KEY RISK FINDINGS\n"
    report += "-----------------\n"
    if critical_risks:
        for risk in critical_risks:
            report += f"- {risk.strip()}\n"
    else:
        report += "- No critical risks identified in the current dataset.\n"
        
    report += "\nACTIONABLE RECOMMENDATIONS\n"
    report += "--------------------------\n"
    if critical_risks:
        report += "1. Immediate Review: Conduct an immediate root-cause analysis on the Critical items listed above.\n"
        report += "2. Policy Update: Ensure compliance policies are updated to reflect the identified high-risk vulnerabilities.\n"
        report += "3. Continuous Monitoring: Increase the monitoring frequency for metrics showing High Risk or severe inconsistency.\n"
        report += "4. Resource Allocation: Shift operational resources to mitigate the identified anomalies before they cascade.\n"
    else:
        report += "1. Maintain Current Posture: Continue standard monitoring as no critical thresholds have been breached.\n"
        report += "2. Process Optimization: Look for efficiency gains in low-risk operational areas.\n"
        
    report += "\n\n-- End of Secure Offline Report --\n"
    return report

def _get_work_dir():
    if "pipeline_work_dir" not in st.session_state or not st.session_state.pipeline_work_dir:
        st.session_state.pipeline_work_dir = tempfile.mkdtemp(prefix="esgrc_run_")
    return st.session_state.pipeline_work_dir

def _render_spinner(text="Processing..."):
    return st.spinner(text)

def render_download_section(pipeline_key: str, total_steps: int, work_dir: str):
    """Renders download buttons for all generated files if the pipeline is fully complete."""
    if st.session_state.get(pipeline_key, {}).get(total_steps) == "completed":
        st.markdown("<br><div class='sec-header'><span>📥</span><span class='sec-header-text'>Download Output Files & Final Reports</span></div>", unsafe_allow_html=True)
        
        if work_dir and os.path.exists(work_dir):
            # Highlight Master and Final Reports First
            master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
            final_esgrc = os.path.join(work_dir, f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.txt")
            final_apex  = os.path.join(work_dir, f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.txt")
            
            # Show APEX Step 8 SPC/RPN report path as well
            final_stat  = os.path.join(work_dir, f"FINAL_STATISTICAL_CLIENT_REPORT_{pe.ANALYSIS_DATE}.txt")

            # Dynamically find ALL final AI report TXT files in work_dir
            import glob
            final_reports = []
            # ESGRC-specific
            for p in [final_esgrc, final_apex, final_stat]:
                if os.path.exists(p):
                    final_reports.append((p, os.path.splitext(os.path.basename(p))[0].replace('_', ' ').title()))
            # Generic modules: FINAL_CLIENT_REPORT_{MODULE}_{DATE}.txt
            for p in sorted(glob.glob(os.path.join(work_dir, "FINAL_CLIENT_REPORT_*.txt"))):
                if p not in [r[0] for r in final_reports]:
                    lbl = os.path.splitext(os.path.basename(p))[0]
                    final_reports.append((p, f"Final AI Report — {lbl.replace('FINAL_CLIENT_REPORT_', '').split('_')[0]}"))

            for path, title in final_reports:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        text_data = f.read()
                    
                    if not text_data.strip():
                        st.warning(f"⚠️ **{title}** — file is empty. Re-run the AI step.")
                        continue

                    st.markdown(f"#### {title}")
                    with st.expander(f"📖 Preview {title}", expanded=True):
                        # Render Claude's markdown output (not raw text)
                        st.markdown(text_data)
                        
                    col1, col2, _ = st.columns([2, 2, 4])
                    with col1:
                        st.download_button(
                            f"⬇️ Download TXT", data=text_data,
                            file_name=os.path.basename(path), mime="text/plain",
                            key=f"dl_txt_{os.path.basename(path)}", use_container_width=True
                        )
                    with col2:
                        try:
                            pdf_data = generate_ai_pdf(text_data, title)
                            st.download_button(
                                f"⬇️ Download PDF", data=pdf_data,
                                file_name=os.path.basename(path).replace(".txt", ".pdf"),
                                mime="application/pdf",
                                key=f"dl_pdf_{os.path.basename(path)}", use_container_width=True
                            )
                        except Exception as e:
                            st.error(f"PDF Error: {e}")
                            
            st.markdown("---")
            st.markdown("#### All Generated Files (including CSVs)")
            all_f   = sorted(os.listdir(work_dir))
            txt_f   = [f for f in all_f if f.endswith(".txt")]
            pdf_f   = [f for f in all_f if f.endswith(".pdf")]
            csv_f   = [f for f in all_f if f.endswith(".csv")]
            
            t_txt, t_pdf, t_csv = st.tabs([f"📄 Text ({len(txt_f)})", f"📊 PDF ({len(pdf_f)})", f"🗂 CSV ({len(csv_f)})"])
            
            for file_list, tab_widget, mime_type in [(txt_f, t_txt, "text/plain"), (pdf_f, t_pdf, "application/pdf"), (csv_f, t_csv, "text/csv")]:
                with tab_widget:
                    if not file_list:
                        st.info("No files generated in this category.")
                    else:
                        cols = st.columns(2)
                        for j, fname in enumerate(file_list):
                            with open(os.path.join(work_dir, fname), "rb") as fh:
                                cols[j % 2].download_button(label=f"⬇️ {fname}", data=fh.read(), file_name=fname, mime=mime_type, key=f"dl_{pipeline_key}_{fname}", use_container_width=True)
        st.divider()
        if st.button("🔁 Run Pipeline Again", use_container_width=True):
            for i in range(1, total_steps + 1):
                st.session_state[pipeline_key][i] = "pending"
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# ESGRC PIPELINE (7 Steps)
# ─────────────────────────────────────────────────────────────────────────────

def render_esgrc_pipeline():
    total_steps = 7
    pipeline_key = "esgrc_pipeline"
    init_pipeline_state(pipeline_key, total_steps)
    work_dir = _get_work_dir()
    st.session_state[f"{pipeline_key}_work_dir"] = work_dir
    
    st.markdown("## ESGRC Analytical Pipeline")
    st.write("This pipeline executes the 7 foundational steps for ESGRC low-performance analysis, SPC charting, and reporting.")
    
    # --- Step 1 ---
    # JSON config is permanently bundled in reference_data — only CSV is needed from user
    _ESGRC_JSON_PATH = os.path.join(
        os.path.dirname(__file__), "modules", "esgrc", "reference_data", "esgrc_performance_json_file.json"
    )

    def render_inputs_step1():
        st.markdown("**Upload Your Metric CSV File:**")
        csv_file = st.file_uploader(
            "Metric CSV (input_metric_values_esgrc.csv)",
            type=["csv"],
            key="esgrc_s1_csv",
            help="Upload the ESGRC metrics CSV. The config JSON is pre-bundled automatically."
        )

        # Auto-load the bundled JSON config
        try:
            with open(_ESGRC_JSON_PATH, "r", encoding="utf-8") as jf:
                j_data = json.load(jf)
            st.success("✅ Config JSON auto-loaded from module reference data.")
        except Exception as e:
            st.error(f"❌ Could not load bundled JSON config: {e}")
            return False, {}

        if csv_file:
            try:
                st.session_state["current_json_data"] = j_data
                with open(os.path.join(work_dir, "input_metric_values_esgrc.csv"), "wb") as f:
                    f.write(csv_file.getvalue())
                return True, {"work_dir": work_dir, "csv_bytes": csv_file.getvalue(), "json_data": j_data}
            except Exception as e:
                st.error(f"Error processing CSV: {e}")
        return False, {}
        
    render_pipeline_step(pipeline_key, 1, total_steps, "Low Performance Analysis",
                         "Computes weighted averages for ESGRC module and identifies low-performing metrics.",
                         render_inputs_step1, pe.run_step1_low_performance_esgrc)
    
    # --- Step 2 ---
    def render_inputs_step2():
        j_data = st.session_state.get("current_json_data")
        if not j_data: return False, {}
        return True, {"work_dir": work_dir, "json_data": j_data}
        
    render_pipeline_step(pipeline_key, 2, total_steps, "Data Split (M / G / Sub-M)",
                         "Splits module values into filtered metrics, groups, and sub-modules.",
                         render_inputs_step2, pe.run_step2_split_esgrc)
                         
    # --- Step 3 ---
    def render_inputs_step3():
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 3, total_steps, "SPC & FMEA X-Bar-R Charts",
                         "X-MR control charts and FMEA RPN scoring for metrics.",
                         render_inputs_step3, pe.run_step3_spc_fmea_esgrc)
                         
    # --- Step 4 ---
    def render_inputs_step4():
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 4, total_steps, "Correlation + CHAID + Fourier",
                         "Correlation matrices, Fourier trend analysis, and CHAID risk segmentation.",
                         render_inputs_step4, pe.run_step4_correlation_chaid_esgrc)
                         
    # --- Step 5 ---
    def render_inputs_step5():
        j_data = st.session_state.get("current_json_data", {})
        return True, {"work_dir": work_dir, "json_data": j_data}
    render_pipeline_step(pipeline_key, 5, total_steps, "Multiple Regression + Risk Scenarios",
                         "Regression suite and Monte Carlo scenario simulations.",
                         render_inputs_step5, pe.run_step5_regression_esgrc)
                         
    # --- Step 6 ---
    def render_inputs_step6():
        return True, {
            "work_dir": work_dir,
            "input_files": [
                os.path.join(work_dir, f"low_performing_entities_report_esgrc_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"metrics_summary_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"M_G_SM_correlation_report_esgrc_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"trends_and_repetitions_report_esgrc_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"inconsistencies_report_esgrc_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"chaid_risk_segmentation_report_esgrc_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"ESGRC_Module_model_summary_{pe.ANALYSIS_DATE}.txt")
            ],
            "output_filename": f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt"
        }
    render_pipeline_step(pipeline_key, 6, total_steps, "Compile Master Report",
                         "Combines all previous text reports into a single consolidated file.",
                         render_inputs_step6, pe.combine_text_reports)
                         
    # --- Step 7 ---
    def render_inputs_step7():
        st.markdown("**AI Interpretation:** Generating a structured AI Executive Summary using AI.")
        return True, {"work_dir": work_dir}
        
    def run_step7_report(work_dir):
        master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
        if not os.path.exists(master_path):
            return False, {}, "Master Consolidated Report not found. Please re-run Step 6."
            
        out_name = f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.txt"
        pdf_name = f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.pdf"
        
        try:
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
                
            from utils.llm_prompts import ESGRC_MODULE_UNIFIED, MODEL_MODULE_UNIFIED, MAX_OUTPUT_TOKENS, HAIKU_UPGRADE_CHAR_THRESHOLD
            import anthropic
            
            full_prompt = ESGRC_MODULE_UNIFIED.replace("{report_text}", content)
            
            model_to_use = MODEL_MODULE_UNIFIED
            if len(content) > HAIKU_UPGRADE_CHAR_THRESHOLD:
                model_to_use = "claude-sonnet-5"
                
            import requests
            import json
            
            headers = {
                "x-api-key": st.secrets.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            data = {
                "model": model_to_use,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [{"role": "user", "content": full_prompt}],
                "stream": True
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, stream=True)
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
            AI_text = ""
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        try:
                            event_data = json.loads(decoded[6:])
                            if event_data.get("type") == "content_block_delta" and event_data.get("delta", {}).get("type") == "text_delta":
                                AI_text += event_data["delta"]["text"]
                        except json.JSONDecodeError:
                            pass
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(AI_text)
                
            pdf_bytes = generate_ai_pdf(AI_text, "FINAL RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [os.path.join(work_dir, out_name), os.path.join(work_dir, pdf_name)]}, "AI Report Generation complete (TXT and PDF generated)."
            
        except Exception as e:
            fallback_text = f"AI Report Generation failed due to API error: {str(e)}"
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(fallback_text)
                
            try:
                pdf_bytes = generate_ai_pdf(fallback_text, "FINAL RECOMMENDED AI REPORT - ERROR")
                with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                    fpdf.write(pdf_bytes)
            except:
                pass
                
            return True, {"files": [
                os.path.join(work_dir, out_name),
                os.path.join(work_dir, pdf_name)
            ]}, f"AI Report Generation Bypassed: {str(e)}"
        
    render_pipeline_step(pipeline_key, 7, total_steps, "Final Output Generation",
                         "Compiles predictive Risk Models and Master Data into final deliverables.",
                         render_inputs_step7, run_step7_report)
                         
    render_download_section(pipeline_key, total_steps, work_dir)


# ─────────────────────────────────────────────────────────────────────────────
# APEX PIPELINE (8 Steps)
# ─────────────────────────────────────────────────────────────────────────────

def render_apex_pipeline():
    total_steps = 6
    pipeline_key = "apex_pipeline"
    init_pipeline_state(pipeline_key, total_steps)
    work_dir = _get_work_dir()
    st.session_state[f"{pipeline_key}_work_dir"] = work_dir
    
    st.markdown("## Enterprise Risk Pipeline")
    st.write("This pipeline executes the full 6-step enterprise-wide L0 consolidation analysis.")
    
    # --- Step 1 ---
    def render_inputs_apex_s1():
        st.markdown("**Upload 12 Required Department Files for L0 Consolidation:**")
        
        required_files = [
            "data_for_risk_assessment_brand.csv",
            "data_for_risk_assessment_bspt.csv",
            "data_for_risk_assessment_customer.csv",
            "data_for_risk_assessment_enterprise.csv",
            "data_for_risk_assessment_esgrc.csv",
            "data_for_risk_assessment_ictm.csv",
            "data_for_risk_assessment_integration.csv",
            "data_for_risk_assessment_mkts.csv",
            "data_for_risk_assessment_product.csv",
            "data_for_risk_assessment_resource.csv",
            "data_for_risk_assessment_service.csv",
            "data_for_risk_assessment_shared.csv"
        ]
        
        uploaded = st.file_uploader("Drop all 12 CSV files here", type=["csv"], accept_multiple_files=True, key="apex_s1_files")
        
        uploaded_names = [f.name for f in uploaded] if uploaded else []
        
        missing_files = [req for req in required_files if req not in uploaded_names]
        missing_count = len(missing_files)
        
        if missing_count == 0 and len(uploaded_names) >= len(required_files):
            st.success("✅ All 12 required files uploaded successfully!")
        else:
            st.markdown("### Upload Checklist")
            for req in required_files:
                if req in uploaded_names:
                    st.markdown(f"<div style='color: #16A34A; margin-bottom: 4px;'>✅ {req}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color: #DC2626; margin-bottom: 4px;'>❌ {req} (Missing)</div>", unsafe_allow_html=True)
                
        if missing_count == 0 and len(uploaded_names) > 0:
            # Write all files to work_dir
            for uf in uploaded:
                with open(os.path.join(work_dir, uf.name), "wb") as f:
                    f.write(uf.getvalue())
            return True, {"work_dir": work_dir}
            
        return False, {}
        
    render_pipeline_step(pipeline_key, 1, total_steps, "All-Module L0 Consolidation",
                         "Consolidates all module risk files into an enterprise L0 view.",
                         render_inputs_apex_s1, pe.run_step6_all_module_consolidation)
                         
    # --- Step 2 to 6 ... (mapping to pipeline engine scripts) ---
    def render_inputs_apex_s2(): return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 2, total_steps, "SPC / FMEA L0 (Enterprise View)",
                         "SPC + Cpk + Sigma Level analysis at enterprise L0 level.",
                         render_inputs_apex_s2, pe.run_step7_spc_fmea_l0)
                         
    def render_inputs_apex_s3(): return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 3, total_steps, "Correlation + CHAID L0 (Enterprise)",
                         "Enterprise-wide correlation, Fourier & CHAID risk segmentation.",
                         render_inputs_apex_s3, pe.run_step8_correlation_chaid_l0)
                         
    def render_inputs_apex_s4():
        st.markdown("Optional: Upload module_mapping.csv and module_matrix.csv")
        map_l0 = st.file_uploader("Module Mapping", key="map_l0")
        mat_l0 = st.file_uploader("Module Matrix", key="mat_l0")
        
        if map_l0:
            with open(os.path.join(work_dir, "module_mapping.csv"), "wb") as f:
                f.write(map_l0.getvalue())
        if mat_l0:
            with open(os.path.join(work_dir, "module_matrix.csv"), "wb") as f:
                f.write(mat_l0.getvalue())
                
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 4, total_steps, "Regression + Risk Scenarios L0",
                         "Full regression suite and Monte Carlo scenarios at enterprise level.",
                         render_inputs_apex_s4, pe.run_step9_regression_l0)
                         
    def render_inputs_apex_s5():
        return True, {
            "work_dir": work_dir,
            "input_files": [
                os.path.join(work_dir, f"performance_report_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"SPC_summary_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"correlation_analysis_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"trends_and_repetitions_report_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"inconsistency_report_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"chaid_risk_segmentation_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, f"L0_Risk_Analysis_Report_{pe.ANALYSIS_DATE}.txt")
            ],
            "output_filename": f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt"
        }
    render_pipeline_step(pipeline_key, 5, total_steps, "Compile Master Report",
                         "Combines all enterprise L0 text reports into a single consolidated file.",
                         render_inputs_apex_s5, pe.combine_text_reports)
                         
    def render_inputs_apex_s6():
        st.markdown("**AI Interpretation:** Generating a structured AI Executive Summary using AI.")
        return True, {"work_dir": work_dir}
        
    def run_step6_report(work_dir):
        if st.session_state.get("is_running_step6", False):
            return False, {}, "A report is already generating in the background. Wait for it to finish."
        st.session_state["is_running_step6"] = True

        try:
            master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
            if not os.path.exists(master_path):
                return False, {}, "Master Consolidated Report not found. Please re-run Step 5."
                
            out_name = f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.txt"
            pdf_name = f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.pdf"
            
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
                
            # Truncate to safely fit within Anthropic's 1 Million token limit (~3.8M chars)
            if len(content) > 3800000:
                content = content[:3800000] + "\n\n[...REPORT TRUNCATED DUE TO 1 MILLION TOKEN API LIMIT...]"
                
            from utils.llm_prompts import APEX_GENERAL_RISK, MODEL_GENERAL_RISK, MAX_OUTPUT_TOKENS
            import anthropic
            import requests
            import json
            
            full_prompt = APEX_GENERAL_RISK.replace("{report_text}", content)
            
            headers = {
                "x-api-key": st.secrets.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
                "content-type": "application/json"
            }
            data = {
                "model": MODEL_GENERAL_RISK,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": full_prompt,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    }
                ],
                "stream": True
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, stream=True)
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
            AI_text = ""
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        try:
                            event_data = json.loads(decoded[6:])
                            if event_data.get("type") == "content_block_delta" and event_data.get("delta", {}).get("type") == "text_delta":
                                AI_text += event_data["delta"]["text"]
                        except json.JSONDecodeError:
                            pass
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(AI_text)
                
            pdf_bytes = generate_ai_pdf(AI_text, "FINAL ENTERPRISE RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [os.path.join(work_dir, out_name), os.path.join(work_dir, pdf_name)]}, "AI Report Generation complete (TXT and PDF generated)."
            
        except Exception as e:
            fallback_text = f"AI Report Generation failed due to API error: {str(e)}"
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(fallback_text)
                
            try:
                pdf_bytes = generate_ai_pdf(fallback_text, "FINAL ENTERPRISE RECOMMENDED AI REPORT - ERROR")
                with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                    fpdf.write(pdf_bytes)
            except:
                pass
                
            return True, {"files": [
                os.path.join(work_dir, out_name),
                os.path.join(work_dir, pdf_name)
            ]}, f"AI Report Generation Bypassed: {str(e)}"
            
        finally:
            st.session_state["is_running_step6"] = False
        
    render_pipeline_step(pipeline_key, 6, total_steps, "Claude Analysis 1 — Final Enterprise Report",
                         "AI-generated executive summary, key risk findings and recommendations for the enterprise.",
                         render_inputs_apex_s6, run_step6_report)

    render_download_section(pipeline_key, total_steps, work_dir)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE REGISTRY  — Single source of truth for all 12 modules
# ─────────────────────────────────────────────────────────────────────────────

MODULE_REGISTRY = {
    "brand":       {"display": "Brand",       "csv": "input_metric_values_brand.csv"},
    "bspt":        {"display": "BSPT",        "csv": "input_metric_values_bspt.csv"},
    "customer":    {"display": "Customer",    "csv": "input_metric_values_customer.csv"},
    "enterprise":  {"display": "Enterprise",  "csv": "input_metric_values_enterprise.csv"},
    "esgrc":       {"display": "ESGRC",       "csv": "input_metric_values_esgrc.csv"},
    "ictm":        {"display": "ICTM",        "csv": "input_metric_values_ictm.csv"},
    "integration": {"display": "Integration", "csv": "input_metric_values_integration.csv"},
    "mkts":        {"display": "MKTS",        "csv": "input_metric_values_mkts.csv"},
    "product":     {"display": "Product",     "csv": "input_metric_values_product.csv"},
    "resource":    {"display": "Resource",    "csv": "input_metric_values_resource.csv"},
    "service":     {"display": "Service",     "csv": "input_metric_values_service.csv"},
    "shared":      {"display": "Shared",      "csv": "input_metric_values_shared.csv"},
}

# All 13 roles available at registration (12 modules + APEX)
ALL_ROLES = ["APEX"] + [v["display"].upper() for v in MODULE_REGISTRY.values()]


def _load_module_json(module_key: str) -> dict:
    """Auto-load the bundled JSON config for a given module."""
    mk   = module_key.lower()
    base = os.path.join(os.path.dirname(__file__), "modules", mk, "reference_data")
    path = os.path.join(base, f"{mk}_performance_json_file.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC MODULE PIPELINE  — One function handles ALL 12 modules
# ─────────────────────────────────────────────────────────────────────────────

def render_module_pipeline(module_key: str):
    """
    Renders the complete 7-step pipeline for any module.
    Identical UI to ESGRC but parameterized — zero duplication.
    """
    mk           = module_key.lower()
    info         = MODULE_REGISTRY.get(mk, {"display": mk.upper(), "csv": f"input_metric_values_{mk}.csv"})
    display_name = info["display"]
    expected_csv = info["csv"]
    total_steps  = 7
    pipeline_key = f"{mk}_pipeline"

    init_pipeline_state(pipeline_key, total_steps)
    work_dir = _get_work_dir()
    st.session_state[f"{pipeline_key}_work_dir"] = work_dir

    st.markdown(f"## {display_name} Analytical Pipeline")
    st.write(f"7-step pipeline for {display_name} low-performance analysis, SPC charting, and AI reporting.")

    # Pre-load bundled JSON (never shown to user)
    j_data = _load_module_json(mk)
    if j_data:
        st.session_state[f"{mk}_json_data"] = j_data
    else:
        st.warning(f"⚠️ Could not load bundled JSON for {display_name}. Check `utils/modules/{mk}/reference_data/`.")

    # ── Step 1: Upload CSV ────────────────────────────────────────────────────
    def render_s1():
        st.markdown(f"**Upload your Metric CSV file** for {display_name}:")
        csv_file = st.file_uploader(
            f"Metric CSV ({expected_csv})", type=["csv"],
            key=f"{mk}_s1_csv",
            help=f"Upload {expected_csv}. Config JSON is pre-bundled automatically."
        )
        jd = st.session_state.get(f"{mk}_json_data", {})
        if jd:
            st.success("✅ Config JSON auto-loaded from reference data.")
        if csv_file and jd:
            try:
                with open(os.path.join(work_dir, expected_csv), "wb") as f:
                    f.write(csv_file.getvalue())
                st.session_state[f"{mk}_csv_bytes"] = csv_file.getvalue()
                st.session_state["current_json_data"] = jd
                return True, {"work_dir": work_dir, "csv_bytes": csv_file.getvalue(),
                               "json_data": jd, "module_key": mk}
            except Exception as e:
                st.error(f"Error: {e}")
        return False, {}

    render_pipeline_step(pipeline_key, 1, total_steps,
                         f"Low Performance Analysis ({display_name})",
                         f"Weighted averages + low-performer identification for {display_name}.",
                         render_s1,
                         lambda work_dir, csv_bytes, json_data, module_key=mk:
                             pe.run_module_step1_low_performance(work_dir, csv_bytes, json_data, module_key))

    # ── Steps 2-7: No extra input needed ─────────────────────────────────────
    jd = st.session_state.get(f"{mk}_json_data", st.session_state.get("current_json_data", {}))

    def _s2_inputs(): return True, {"work_dir": work_dir, "json_data": jd, "module_key": mk}
    render_pipeline_step(pipeline_key, 2, total_steps, f"Data Split — M / G / Sub-M",
                         "Splits data into metrics, groups, and sub-modules CSVs.",
                         _s2_inputs,
                         lambda work_dir, json_data, module_key=mk:
                             pe.run_module_step2_split(work_dir, json_data, module_key))

    def _s3_inputs(): return True, {"work_dir": work_dir, "module_key": mk}
    render_pipeline_step(pipeline_key, 3, total_steps, "SPC & FMEA X-Bar-R Charts",
                         "X-MR control charts and FMEA RPN scoring.",
                         _s3_inputs,
                         lambda work_dir, module_key=mk:
                             pe.run_module_step3_spc_fmea(work_dir, module_key))

    def _s4_inputs(): return True, {"work_dir": work_dir, "module_key": mk}
    render_pipeline_step(pipeline_key, 4, total_steps, "Correlation + CHAID + Fourier",
                         "Correlation matrices, Fourier trend analysis, and CHAID risk segmentation.",
                         _s4_inputs,
                         lambda work_dir, module_key=mk:
                             pe.run_module_step4_correlation_chaid(work_dir, module_key))

    def _s5_inputs(): return True, {"work_dir": work_dir, "json_data": jd, "module_key": mk}
    render_pipeline_step(pipeline_key, 5, total_steps, "Multiple Regression + Risk Scenarios",
                         "Regression suite and Monte Carlo scenario simulations.",
                         _s5_inputs,
                         lambda work_dir, json_data, module_key=mk:
                             pe.run_module_step5_regression(work_dir, json_data, module_key))

    def _s6_inputs(): return True, {"work_dir": work_dir, "module_key": mk}
    render_pipeline_step(pipeline_key, 6, total_steps, "Compile Master Report",
                         "Combines all analysis reports into a single consolidated file.",
                         _s6_inputs,
                         lambda work_dir, module_key=mk:
                             pe.run_module_step6_compile_report(work_dir, module_key))

    def _s7_inputs():
        st.markdown("**AI Interpretation:** Generating a structured AI Executive Summary.")
        return True, {"work_dir": work_dir, "module_key": mk}
    render_pipeline_step(pipeline_key, 7, total_steps, "Final AI Report Generation",
                         "Claude AI analyses all reports and generates the final executive summary.",
                         _s7_inputs,
                         lambda work_dir, module_key=mk:
                             pe.run_module_step7_ai_report(work_dir, module_key))

    render_download_section(pipeline_key, total_steps, work_dir)
