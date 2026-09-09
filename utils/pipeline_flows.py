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
            master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
            final_esgrc = os.path.join(work_dir, f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.txt")
            final_apex  = os.path.join(work_dir, f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.txt")
            
            for path, title in [(final_esgrc, "Final Recommended AI Report (ESGRC)"),
                                (final_apex, "Final Recommended AI Report (Enterprise Risk)")]:
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
        from groq import Groq
        master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
        if not os.path.exists(master_path):
            return False, {}, "Master Consolidated Report not found. Please re-run Step 6."
            
        out_name = f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.txt"
        pdf_name = f"FINAL_CLIENT_REPORT_ESGRC_{pe.ANALYSIS_DATE}.pdf"
        
        try:
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
                
            from utils.master_pdf import generate_master_pdf_bytes
            import base64
            
            pdf_bytes_for_llm = generate_master_pdf_bytes(content)
            pdf_base64 = base64.b64encode(pdf_bytes_for_llm).decode('utf-8')
            
            import anthropic
            client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY", ""))
            sys_prompt = "You are an expert ESGRC risk analyst. Analyze the attached consolidated report and provide a comprehensive structured executive summary, key risk findings, and actionable recommendations. Be detailed but clear."
            
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=8192,
                system=sys_prompt,
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "Please analyze this report."
                            }
                        ]
                    }
                ]
            )
            AI_text = "".join(block.text for block in response.content if block.type == "text")
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(AI_text)
                
            pdf_bytes = generate_ai_pdf(AI_text, "FINAL RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [out_name, pdf_name]}, "AI Report Generation complete (TXT & PDF generated)."
            
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
                
            return True, {"files": [out_name, pdf_name]}, f"AI Report Generation Bypassed: {str(e)}"
        
    render_pipeline_step(pipeline_key, 7, total_steps, "Final Output Generation",
                         "Compiles predictive Risk Models and Master Data into final deliverables.",
                         render_inputs_step7, run_step7_report)
                         
    render_download_section(pipeline_key, total_steps, work_dir)


# ─────────────────────────────────────────────────────────────────────────────
# APEX PIPELINE (8 Steps)
# ─────────────────────────────────────────────────────────────────────────────

def render_apex_pipeline():
    total_steps = 8
    pipeline_key = "apex_pipeline"
    init_pipeline_state(pipeline_key, total_steps)
    work_dir = _get_work_dir()
    
    st.markdown("## Enterprise Risk Pipeline")
    st.write("This pipeline executes the full 8-step enterprise-wide L0 consolidation analysis.")
    
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
        from groq import Groq
        master_path = os.path.join(work_dir, f"MASTER_CONSOLIDATED_REPORT_{pe.ANALYSIS_DATE}.txt")
        if not os.path.exists(master_path):
            return False, {}, "Master Consolidated Report not found. Please re-run Step 5."
            
        out_name = f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.txt"
        pdf_name = f"FINAL_ENTERPRISE_REPORT_{pe.ANALYSIS_DATE}.pdf"
        
        try:
            with open(master_path, "r", encoding="utf-8") as fin:
                content = fin.read()
                
            from utils.master_pdf import generate_master_pdf_bytes
            import base64
            
            pdf_bytes_for_llm = generate_master_pdf_bytes(content)
            pdf_base64 = base64.b64encode(pdf_bytes_for_llm).decode('utf-8')
            
            import anthropic
            client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY", ""))
            sys_prompt = "You are an expert Enterprise Risk analyst. Analyze the attached consolidated L0 enterprise report and provide a comprehensive structured executive summary, key enterprise risk findings, and actionable recommendations. Be detailed but clear."
            
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=8192,
                system=sys_prompt,
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "Please analyze this report."
                            }
                        ]
                    }
                ]
            )
            AI_text = "".join(block.text for block in response.content if block.type == "text")
            
            with open(os.path.join(work_dir, out_name), "w", encoding="utf-8") as fout:
                fout.write(AI_text)
                
            pdf_bytes = generate_ai_pdf(AI_text, "FINAL ENTERPRISE RECOMMENDED AI REPORT")
            with open(os.path.join(work_dir, pdf_name), "wb") as fpdf:
                fpdf.write(pdf_bytes)
                
            return True, {"files": [out_name, pdf_name]}, "AI Report Generation complete (TXT & PDF generated)."
            
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
                
            return True, {"files": [out_name, pdf_name]}, f"AI Report Generation Bypassed: {str(e)}"
        
    render_pipeline_step(pipeline_key, 6, total_steps, "Final Output Generation",
                         "Compiles predictive Risk Models and Master Data into final deliverables.",
                         render_inputs_apex_s6, run_step6_report)

    def render_inputs_apex_s7():
        st.markdown("**Combiner:** Merging SPC and RPN statistical reports.")
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 7, total_steps, "Combine SPC, Six Sigma and RPN reports",
                         "Consolidated input file for LLM interpretation of the statistical reports.",
                         render_inputs_apex_s7, pe.run_step10_combine_spc_rpn)

    def render_inputs_apex_s8():
        st.markdown("**Claude Analysis 2:** Analyzing SPC trends and DPMO calculations.")
        return True, {"work_dir": work_dir}
    render_pipeline_step(pipeline_key, 8, total_steps, "Claude Analysis 2 (SPC Six Sigma and RPN)",
                         "Generate a detailed report with recommendations and action items.",
                         render_inputs_apex_s8, pe.run_step11_claude_analysis_2)

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
