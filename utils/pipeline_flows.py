import streamlit as st
import os
import json
import tempfile
import pandas as pd
import utils.pipeline_engine as pe
from utils.pipeline_ui import init_pipeline_state, render_pipeline_step

def generate_ai_pdf(text, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    import io
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], textColor=HexColor("#0C4A6E"), spaceAfter=20)
    h1_style = ParagraphStyle('H1', parent=styles['Heading2'], textColor=HexColor("#0284C7"), spaceBefore=15, spaceAfter=10)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], spaceAfter=10, leading=14)
    
    story = [Paragraph(title, title_style)]
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Basic markdown parsing for the PDF
        clean_line = line.replace('**', '')
        if line.startswith('### '):
            story.append(Paragraph(clean_line[4:], h1_style))
        elif line.startswith('## '):
            story.append(Paragraph(clean_line[3:], h1_style))
        elif line.startswith('# '):
            story.append(Paragraph(clean_line[2:], h1_style))
        elif line.startswith('- ') or line.startswith('* '):
            story.append(Paragraph("• " + clean_line[2:], body_style))
        else:
            story.append(Paragraph(clean_line, body_style))
            
    doc.build(story)
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
            master_path = os.path.join(work_dir, "MASTER_CONSOLIDATED_REPORT.txt")
            final_esgrc = os.path.join(work_dir, "FINAL_CLIENT_REPORT_ESGRC.txt")
            final_apex  = os.path.join(work_dir, "FINAL_ENTERPRISE_REPORT.txt")
            
            for path, title in [(final_esgrc, "Final Recommended AI Report (ESGRC)"),
                                (final_apex, "Final Recommended AI Report (APEX)")]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        text_data = f.read()
                    
                    st.markdown(f"#### {title}")
                    with st.expander(f"📖 Preview {title}", expanded=False):
                        st.text_area(f"{title} Content", text_data, height=300, label_visibility="collapsed")
                        
                    col1, col2, _ = st.columns([2, 2, 4])
                    with col1:
                        st.download_button(f"⬇️ Download TXT", data=text_data, file_name=os.path.basename(path), mime="text/plain", key=f"dl_txt_{os.path.basename(path)}", use_container_width=True)
                    with col2:
                        try:
                            pdf_data = None
                            if "FINAL" in path:
                                pdf_data = generate_ai_pdf(text_data, title)
                            else:
                                from utils.master_pdf import generate_master_pdf_bytes
                                pdf_data = generate_master_pdf_bytes(text_data)
                                
                            st.download_button(f"⬇️ Download PDF", data=pdf_data, file_name=os.path.basename(path).replace(".txt", ".pdf"), mime="application/pdf", key=f"dl_pdf_{os.path.basename(path)}", use_container_width=True)
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
    
    st.markdown("## ESGRC Analytical Pipeline")
    st.write("This pipeline executes the 7 foundational steps for ESGRC low-performance analysis, SPC charting, and reporting.")
    
    # --- Step 1 ---
    def render_inputs_step1():
        st.markdown("**Upload Required Files:**")
        csv_file = st.file_uploader("1. Metric CSV (input_metric_values_esgrc.csv)", type=["csv"], key="esgrc_s1_csv")
        json_file = st.file_uploader("2. Config JSON (esgrc_performance_json_file.json)", type=["json"], key="esgrc_s1_json")
        
        if csv_file and json_file:
            try:
                j_data = json.loads(json_file.read())
                st.session_state["current_json_data"] = j_data
                # Write csv to work_dir so next scripts can find it
                with open(os.path.join(work_dir, "input_metric_values_esgrc.csv"), "wb") as f:
                    f.write(csv_file.getvalue())
                return True, {"work_dir": work_dir, "csv_bytes": csv_file.getvalue(), "json_data": j_data}
            except Exception as e:
                st.error(f"Invalid JSON file: {e}")
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
                os.path.join(work_dir, "low_performing_entities_report_esgrc.txt"),
                os.path.join(work_dir, f"metrics_summary_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, "M_G_SM_correlation_report_esgrc.txt"),
                os.path.join(work_dir, "trends_and_repetitions_report_esgrc.txt"),
                os.path.join(work_dir, "inconsistencies_report_esgrc.txt"),
                os.path.join(work_dir, "chaid_risk_segmentation_report_esgrc.txt"),
                os.path.join(work_dir, "ESGRC_Module_model_summary.txt")
            ],
            "output_filename": "MASTER_CONSOLIDATED_REPORT.txt"
        }
    render_pipeline_step(pipeline_key, 6, total_steps, "Compile Master Report",
                         "Combines all previous text reports into a single consolidated file.",
                         render_inputs_step6, pe.combine_text_reports)
                         
    # --- Step 7 ---
    def render_inputs_step7():
        st.markdown("**LLM Interpretation:** The backend will now interpret the Master Report using Anthropic Claude to generate a structured AI Executive Summary in both TXT and PDF formats.")
        return True, {"work_dir": work_dir}
        
    def run_step7_report(work_dir):
        import anthropic
        master_path = os.path.join(work_dir, "MASTER_CONSOLIDATED_REPORT.txt")
        if not os.path.exists(master_path):
            return False, {}, "Master Consolidated Report not found. Please re-run Step 6."
            
        try:
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
            
            client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY"))
            sys_prompt = "You are an expert ESGRC risk analyst. Analyze the following consolidated report and provide a comprehensive structured executive summary, key risk findings, and actionable recommendations. Be detailed but clear."
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                temperature=0.2,
                system=sys_prompt,
                messages=[{"role": "user", "content": content}]
            )
            llm_text = response.content[0].text
            
            out_name = "FINAL_CLIENT_REPORT_ESGRC.txt"
            pdf_name = "FINAL_CLIENT_REPORT_ESGRC.pdf"
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(llm_text)
                
            pdf_bytes = generate_ai_pdf(llm_text, "FINAL RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [out_name, pdf_name]}, "AI Report Generation complete (TXT & PDF generated)."
        except Exception as e:
            return False, {}, f"Anthropic API Error: {str(e)}"
        
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
    
    st.markdown("## Enterprise APEX Pipeline")
    st.write("This pipeline executes the full 8-step enterprise-wide L0 consolidation analysis.")
    
    # --- Step 1 ---
    def render_inputs_apex_s1():
        st.markdown("**Upload 12 Required Department Files for L0 Consolidation:**")
        
        required_files = [
            "data_for_risk_assessment_brand.csv",
            "data_for_risk_assessment_bspt.csv",
            "data_for_risk_assessment_customer.csv",
            "data_for_risk_assessment_esgrc.csv",
            "data_for_risk_assessment_integration.csv",
            "data_for_risk_assessment_it.csv",
            "data_for_risk_assessment_legal.csv",
            "data_for_risk_assessment_ops.csv",
            "data_for_risk_assessment_physical.csv",
            "data_for_risk_assessment_regulatory.csv",
            "data_for_risk_assessment_strategic.csv",
            "data_for_risk_assessment_vendor.csv"
        ]
        
        uploaded = st.file_uploader("Drop all 12 CSV files here", type=["csv"], accept_multiple_files=True, key="apex_s1_files")
        
        uploaded_names = [f.name for f in uploaded] if uploaded else []
        
        st.markdown("### Upload Checklist")
        missing_count = 0
        for req in required_files:
            if req in uploaded_names:
                st.markdown(f"<div style='color: #16A34A; margin-bottom: 4px;'>✅ {req}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='color: #DC2626; margin-bottom: 4px;'>❌ {req} (Missing)</div>", unsafe_allow_html=True)
                missing_count += 1
                
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
        st.file_uploader("Module Mapping", key="map_l0")
        st.file_uploader("Module Matrix", key="mat_l0")
        # In a real impl, we'd save these. For now, just return true.
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 4, total_steps, "Regression + Risk Scenarios L0",
                         "Full regression suite and Monte Carlo scenarios at enterprise level.",
                         render_inputs_apex_s4, pe.run_step9_regression_l0)
                         
    def render_inputs_apex_s5():
        return True, {
            "work_dir": work_dir,
            "input_files": [
                os.path.join(work_dir, "performance_report_2025.txt"),
                os.path.join(work_dir, f"SPC_summary_L0_{pe.ANALYSIS_DATE}.txt"),
                os.path.join(work_dir, "correlation_analysis_L0.txt"),
                os.path.join(work_dir, "trends_and_repetitions_report_L0.txt"),
                os.path.join(work_dir, "inconsistency_report_L0.txt"),
                os.path.join(work_dir, "chaid_risk_segmentation_L0.txt"),
                os.path.join(work_dir, "L0_Risk_Analysis_Report_2025.txt")
            ],
            "output_filename": "MASTER_CONSOLIDATED_REPORT.txt"
        }
    render_pipeline_step(pipeline_key, 5, total_steps, "Compile Master Report",
                         "Combines all enterprise L0 text reports into a single consolidated file.",
                         render_inputs_apex_s5, pe.combine_text_reports)
                         
    def render_inputs_apex_s6():
        st.markdown("**LLM Interpretation:** The backend will now interpret the Master Report using Anthropic Claude to generate a structured AI Executive Summary in both TXT and PDF formats.")
        return True, {"work_dir": work_dir}
        
    def run_step6_report(work_dir):
        import anthropic
        master_path = os.path.join(work_dir, "MASTER_CONSOLIDATED_REPORT.txt")
        if not os.path.exists(master_path):
            return False, {}, "Master Consolidated Report not found. Please re-run Step 5."
            
        try:
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
            
            client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY"))
            sys_prompt = "You are an expert Enterprise APEX risk analyst. Analyze the following consolidated L0 enterprise report and provide a comprehensive structured executive summary, key enterprise risk findings, and actionable recommendations. Be detailed but clear."
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                temperature=0.2,
                system=sys_prompt,
                messages=[{"role": "user", "content": content}]
            )
            llm_text = response.content[0].text
            
            out_name = "FINAL_ENTERPRISE_REPORT.txt"
            pdf_name = "FINAL_ENTERPRISE_REPORT.pdf"
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(llm_text)
                
            pdf_bytes = generate_ai_pdf(llm_text, "FINAL ENTERPRISE RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [out_name, pdf_name]}, "AI Report Generation complete (TXT & PDF generated)."
        except Exception as e:
            return False, {}, f"Anthropic API Error: {str(e)}"
        
    render_pipeline_step(pipeline_key, 6, total_steps, "Final Output Generation",
                         "Compiles predictive Risk Models and Master Data into final deliverables.",
                         render_inputs_apex_s6, run_step6_report)

    render_download_section(pipeline_key, total_steps, work_dir)
