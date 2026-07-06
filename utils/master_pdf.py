import os
import re
import csv
import io
import ast
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
    PageBreak
)

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR PALETTE (Sky Blue + White corporate branding)
# ─────────────────────────────────────────────────────────────────────────────
SKY_DARK   = HexColor("#0284C7")
SKY_MID    = HexColor("#0EA5E9")
SKY_LIGHT  = HexColor("#BAE6FD")
SKY_PALE   = HexColor("#F0F9FF")
INK_DARK   = HexColor("#0C4A6E")
INK_GRAY   = HexColor("#475569")
WHITE      = colors.white
GREEN      = HexColor("#10B981")
AMBER      = HexColor("#F59E0B")
RED        = HexColor("#EF4444")
LIGHT_GRAY = HexColor("#F8FAFC")
ROW_ALT    = HexColor("#E0F2FE")

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm

# ─────────────────────────────────────────────────────────────────────────────
# TYPOGRAPHY & PARAGRAPH STYLES
# ─────────────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def get_styles():
    s = {}
    s["title"] = ParagraphStyle(
        "DocTitle",
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=INK_DARK,
        spaceAfter=8,
    )
    s["subtitle"] = ParagraphStyle(
        "DocSubtitle",
        fontName="Helvetica",
        fontSize=11,
        textColor=INK_GRAY,
        spaceAfter=20,
    )
    s["section_h1"] = ParagraphStyle(
        "SectionH1",
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=INK_DARK,
        spaceBefore=22,
        spaceAfter=12,
    )
    s["section_h2"] = ParagraphStyle(
        "SectionH2",
        fontName="Helvetica-Bold",
        fontSize=11.5,
        textColor=SKY_DARK,
        spaceBefore=14,
        spaceAfter=8,
    )
    s["body"] = ParagraphStyle(
        "BodyTextCustom",
        fontName="Helvetica",
        fontSize=9.5,
        textColor=INK_GRAY,
        leading=14.5,
        spaceAfter=8,
    )
    s["body_bold"] = ParagraphStyle(
        "BodyTextBold",
        parent=s["body"],
        fontName="Helvetica-Bold",
        textColor=INK_DARK,
    )
    s["bullet"] = ParagraphStyle(
        "BulletCustom",
        parent=s["body"],
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=5,
    )
    s["tbl_header"] = ParagraphStyle(
        "TableHeaderCustom",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=WHITE,
        alignment=TA_LEFT,
    )
    s["tbl_cell"] = ParagraphStyle(
        "TableCellCustom",
        fontName="Helvetica",
        fontSize=8.5,
        textColor=INK_DARK,
        leading=11.5,
    )
    s["tbl_cell_bold"] = ParagraphStyle(
        "TableCellBold",
        parent=s["tbl_cell"],
        fontName="Helvetica-Bold",
    )
    s["tbl_cell_id"] = ParagraphStyle(
        "TableCellId",
        parent=s["tbl_cell"],
        fontName="Helvetica-Bold",
        textColor=SKY_DARK,
    )
    s["monospace_card"] = ParagraphStyle(
        "MonospaceCard",
        fontName="Courier",
        fontSize=7.5,
        textColor=colors.HexColor("#1E293B"),
        leading=10,
        spaceAfter=5,
    )
    s["meta_label"] = ParagraphStyle(
        "MetaLabel",
        fontName="Helvetica",
        fontSize=8.5,
        textColor=INK_GRAY,
    )
    s["meta_value"] = ParagraphStyle(
        "MetaValue",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=INK_DARK,
    )
    s["disclaimer"] = ParagraphStyle(
        "DisclaimerCustom",
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=INK_GRAY,
        leading=12,
        borderPad=6,
        borderColor=SKY_LIGHT,
        borderWidth=0.5,
        backColor=SKY_PALE,
        spaceBefore=18,
    )
    return s

s = get_styles()

# ─────────────────────────────────────────────────────────────────────────────
# HEADER & FOOTER CANVAS FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def draw_cover_background(canvas, doc):
    canvas.saveState()
    # Vertical color sidebar on the cover page
    canvas.setFillColor(SKY_DARK)
    canvas.rect(0, 0, 1.5 * cm, PAGE_H, fill=1, stroke=0)
    
    canvas.setFillColor(SKY_MID)
    canvas.rect(1.5 * cm, 0, 0.2 * cm, PAGE_H, fill=1, stroke=0)
    
    # Bottom watermark
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(INK_GRAY)
    canvas.drawString(2.2 * cm, 1.2 * cm, "RISK INTELL Platform — Enterprise Intelligence Consolidated Report")
    canvas.drawRightString(PAGE_W - MARGIN, 1.2 * cm, "Confidential")
    canvas.restoreState()

def draw_header_footer(canvas, doc):
    canvas.saveState()
    
    # ── HEADER ──
    # Top banner background
    canvas.setFillColor(SKY_DARK)
    canvas.rect(0, PAGE_H - 2.5 * cm, PAGE_W, 2.5 * cm, fill=1, stroke=0)
    # Accent line
    canvas.setFillColor(SKY_MID)
    canvas.rect(0, PAGE_H - 2.62 * cm, PAGE_W, 0.12 * cm, fill=1, stroke=0)
    
    # Branded Logo / Title
    canvas.setFont("Helvetica-Bold", 14)
    canvas.setFillColor(WHITE)
    canvas.drawString(MARGIN, PAGE_H - 1.2 * cm, "🛡  RISK INTELL Platform")
    
    # Subtitle
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#BAE6FD"))
    canvas.drawString(MARGIN, PAGE_H - 1.8 * cm, "Enterprise ESG · Risk · Compliance — Pipeline Automation Consolidated Report")
    
    # Page Number (Page 2, 3, etc.)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.5 * cm, f"Page {doc.page}")
    
    # ── FOOTER ──
    canvas.setFillColor(SKY_LIGHT)
    canvas.rect(0, 0, PAGE_W, 1.0 * cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(INK_GRAY)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    canvas.drawString(MARGIN, 0.38 * cm, f"Generated: {ts}  |  Master Consolidated Report  |  Confidential")
    canvas.drawRightString(PAGE_W - MARGIN, 0.38 * cm, "© RISK INTELL")
    
    canvas.restoreState()

# ─────────────────────────────────────────────────────────────────────────────
# HELPER TABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def build_styled_table(headers_list, rows_list, col_widths=None):
    """Build a beautifully styled ReportLab table."""
    data = []
    
    # Wrap header cells in Paragraph
    header_row = [Paragraph(f"<b>{h}</b>", s["tbl_header"]) for h in headers_list]
    data.append(header_row)
    
    # Wrap data cells in Paragraph
    for row in rows_list:
        data_row = []
        for c in row:
            if isinstance(c, Paragraph):
                data_row.append(c)
            else:
                c_str = str(c)
                if re.match(r"^[A-Z]{3}\d{5}$", c_str):
                    data_row.append(Paragraph(c_str, s["tbl_cell_id"]))
                else:
                    data_row.append(Paragraph(c_str, s["tbl_cell"]))
        data.append(data_row)
        
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    
    t_style = TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), SKY_DARK),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
        ("GRID",         (0, 0), (-1, -1), 0.4, SKY_LIGHT),
        ("LEFTPADDING",  (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING",   (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
    ])
    
    for r in range(1, len(data)):
        t_style.add("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 0 else WHITE)
        
    tbl.setStyle(t_style)
    return tbl

# ─────────────────────────────────────────────────────────────────────────────
# STYLING HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def score_color_style(v):
    try:
        val = float(v)
        if val <= 1.0:
            val = val * 100
        if val >= 85:
            return ParagraphStyle("sc_g", parent=s["tbl_cell_bold"], textColor=GREEN)
        if val >= 75:
            return ParagraphStyle("sc_a", parent=s["tbl_cell_bold"], textColor=AMBER)
        return ParagraphStyle("sc_r", parent=s["tbl_cell_bold"], textColor=RED)
    except:
        return s["tbl_cell_bold"]

def corr_color_style(v):
    try:
        val = float(v)
        if abs(val) >= 0.5:
            return ParagraphStyle("corr_s", parent=s["tbl_cell_bold"], textColor=RED)
        if abs(val) >= 0.2:
            return ParagraphStyle("corr_m", parent=s["tbl_cell_bold"], textColor=AMBER)
        return s["tbl_cell"]
    except:
        return s["tbl_cell"]

# ─────────────────────────────────────────────────────────────────────────────
# PARSERS FOR THE SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def parse_txt_content(content):
    """Split the consolidated report content by REPORT HEADER."""
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
        
    content = content_sub

    parts = re.split(r"={5,}\s*REPORT HEADER: (.*?)\s*={5,}", content)
    sections = {}
    for i in range(1, len(parts), 2):
        sections[parts[i].strip()] = parts[i+1].strip()
    return sections

def parse_model_summary(text):
    data = {"MSE": "N/A", "Confidence": "N/A", "Risk": "N/A", "Scenarios": [], "Actions": []}
    
    m_mse = re.search(r"Average MSE[^:]*:\s*([\d\.]+)", text, re.IGNORECASE)
    if m_mse:
        data["MSE"] = m_mse.group(1)
        
    m_conf = re.search(r"Risk Confidence Score:\s*(\w+)", text, re.IGNORECASE)
    if m_conf:
        data["Confidence"] = m_conf.group(1)
        
    m_risk = re.search(r"Overall Risk:\s*([\d\.]+)", text, re.IGNORECASE)
    if m_risk:
        data["Risk"] = m_risk.group(1)
        
    sc_section = re.search(r"Risk Scenarios [^:]*:\s*(.*?)(?:Follow-up|Recommendations|End of|$)", text, re.DOTALL | re.IGNORECASE)
    if sc_section:
        sc_text = sc_section.group(1)
        for line in sc_text.split('\n'):
            line_s = line.strip()
            if ":" in line_s:
                parts = line_s.split(":")
                name = parts[0].strip()
                val = parts[1].strip()
                data["Scenarios"].append([name, val])
                
    act_section = re.search(r"Follow-up Actions:\s*(.*?)(?:End of|$)", text, re.DOTALL | re.IGNORECASE)
    if act_section:
        act_text = act_section.group(1)
        for line in act_text.split('\n'):
            line_s = line.strip()
            if line_s.startswith("-") or line_s.startswith("•") or re.match(r"^\d+\.", line_s):
                line_s = re.sub(r"^[-•\d\.]+\s*", "", line_s)
            if line_s:
                data["Actions"].append(line_s)
                
    return data

def parse_l0_risk_report(text):
    data = {"Risk": "N/A", "MSE": "N/A", "Confidence": "N/A", "Scenarios": [], "Actions": [], "Metrics": {}}
    
    m_risk = re.search(r"[aA]\.\s*Overall Risk:\s*([\d\.]+)", text)
    if m_risk:
        data["Risk"] = m_risk.group(1)
        
    m_mse = re.search(r"[cC]\.\s*Average MSE:\s*([\d\.\-eE]+)", text)
    if m_mse:
        data["MSE"] = m_mse.group(1)
        
    m_conf = re.search(r"[hH]\.\s*Risk Confidence Score:\s*(\w+)", text)
    if m_conf:
        data["Confidence"] = m_conf.group(1)
        
    sc_section = re.search(r"[bB]\.\s*Top Ten Risk Scenarios:\s*(.*?)(?=[cCdD]\.|$)", text, re.DOTALL)
    if sc_section:
        for line in sc_section.group(1).split('\n'):
            line_s = line.strip()
            if ":" in line_s:
                parts = line_s.split(":")
                data["Scenarios"].append([parts[0].strip(), parts[1].strip()])
                
    act_section = re.search(r"[dD]\.\s*Follow-up Actions:\s*(.*?)(?=[eE]\.|$)", text, re.DOTALL)
    if act_section:
        for line in act_section.group(1).split('\n'):
            line_s = line.strip()
            if line_s:
                line_s = re.sub(r"^\d+\.\s*", "", line_s)
                data["Actions"].append(line_s)
                
    met_section = re.search(r"[eE]\.\s*Metrics in High-Risk Scenarios:\s*(.*?)(?=[fFgGhH]\.|$)", text, re.DOTALL)
    if met_section:
        curr_sc = None
        for line in met_section.group(1).split('\n'):
            line_s = line.strip()
            if not line_s:
                continue
            if re.match(r"^\d+\.\s*Scenario_", line_s):
                curr_sc = re.sub(r"^\d+\.\s*", "", line_s).replace(":", "").strip()
                data["Metrics"][curr_sc] = []
            elif line_s.startswith("-") and curr_sc:
                m_detail = re.sub(r"^-\s*", "", line_s).strip()
                data["Metrics"][curr_sc].append(m_detail)
                
    return data

def parse_low_performers(text):
    sub_sections = {}
    current_key = None
    current_lines = []
    
    for line in text.split('\n'):
        line_s = line.strip()
        if not line_s:
            continue
        if "Low-Performing" in line_s:
            if current_key and current_lines:
                sub_sections[current_key] = current_lines
            current_key = line_s
            current_lines = []
        else:
            current_lines.append(line_s)
            
    if current_key and current_lines:
        sub_sections[current_key] = current_lines
        
    parsed_tables = {}
    for title, lines_list in sub_sections.items():
        csv_data = "\n".join(lines_list)
        reader = csv.reader(io.StringIO(csv_data))
        rows = list(reader)
        parsed_tables[title] = rows
        
    return parsed_tables

def parse_tsv_table(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return []
    rows = []
    for line in lines:
        rows.append(line.split('\t'))
    return rows

def parse_inconsistencies(text):
    data = {"dependent": [], "independent": []}
    
    dep_match = re.search(r"Dependent Inconsistencies:\s*(.*?)(?:Independent Inconsistencies:|$)", text, re.DOTALL)
    if dep_match:
        lines = [l.strip() for l in dep_match.group(1).split('\n') if l.strip()]
        for line in lines:
            if "|" in line:
                data["dependent"].append([x.strip() for x in line.split('|')])
            elif line.lower() != "none found.":
                data["dependent"].append([line])
                
    ind_match = re.search(r"Independent Inconsistencies:\s*(.*)", text, re.DOTALL)
    if ind_match:
        lines = [l.strip() for l in ind_match.group(1).split('\n') if l.strip()]
        for line in lines:
            if "|" in line:
                data["independent"].append([x.strip() for x in line.split('|')])
            elif line.lower() != "none found.":
                data["independent"].append([line])
                
    return data

def parse_trends_repetitions(text):
    data = {"trends": {}, "repetitions": {}}
    
    trends_match = re.search(r"Trends:\s*(.*?)(?:Repetitions|$)", text, re.DOTALL | re.IGNORECASE)
    if not trends_match:
        trends_match = re.search(r"Metrics Trends:\s*(.*?)(?:Repetitions|$)", text, re.DOTALL | re.IGNORECASE)
        
    if trends_match:
        for line in trends_match.group(1).split('\n'):
            line_s = line.strip()
            if ":" in line_s:
                parts = line_s.split(":")
                data["trends"][parts[0].strip()] = parts[1].strip()
                
    rep_match = re.search(r"Repetitions [^:]*:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if rep_match:
        for line in rep_match.group(1).split('\n'):
            line_s = line.strip()
            if ":" in line_s:
                parts = line_s.split(":")
                data["repetitions"][parts[0].strip()] = parts[1].strip()
                
    return data

def parse_chaid_report(text):
    data = {"tree": "", "distribution": [], "high_risk_metrics": []}
    
    tree_match = re.search(r"Tree Summary:\s*(.*?)(?:Risk Level Distribution|$)", text, re.DOTALL | re.IGNORECASE)
    if not tree_match:
         tree_match = re.search(r"CHAID Tree Summary:\s*(.*?)(?:Risk Level Distribution|$)", text, re.DOTALL | re.IGNORECASE)
    if tree_match:
        data["tree"] = tree_match.group(1).strip()
        
    dist_match = re.search(r"Risk Level Distribution:\s*(.*?)(?:High-Risk Metrics|High Risk Metrics|Notes|$)", text, re.DOTALL | re.IGNORECASE)
    if dist_match:
        lines = [l.strip() for l in dist_match.group(1).split('\n') if l.strip()]
        for line in lines:
            parts = re.split(r'\s{2,}', line)
            if len(parts) == 1:
                parts = line.split('\t')
            if len(parts) == 1:
                parts = [x.strip() for x in line.split(' ') if x.strip()]
            if len(parts) >= 2:
                data["distribution"].append(parts)
                
    hr_match = re.search(r"High-Risk Metrics:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if not hr_match:
        hr_match = re.search(r"High Risk Metrics:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
        
    if hr_match:
        lines = [l.strip() for l in hr_match.group(1).split('\n') if l.strip()]
        for line in lines:
            parts = re.split(r'\s{2,}', line)
            if len(parts) == 1:
                parts = line.split('\t')
            if len(parts) == 1:
                parts = [x.strip() for x in line.split(' ') if x.strip()]
            if len(parts) >= 2:
                data["high_risk_metrics"].append(parts)
                
    return data

def parse_chaid_tree_to_rows(tree_str):
    try:
        tree_str_clean = re.sub(r"^.*?CHAID Tree Summary:\s*", "", tree_str, flags=re.IGNORECASE).strip()
        start_idx = tree_str_clean.find('[')
        end_idx = tree_str_clean.rfind(']')
        if start_idx != -1 and end_idx != -1:
            list_str = tree_str_clean[start_idx:end_idx+1]
            tree_list = ast.literal_eval(list_str)
            rows = []
            for item in tree_list:
                path = " → ".join(item[0]) if item[0] else "Root Node"
                dist_parts = []
                for risk, val in item[1].items():
                    dist_parts.append(f"{risk}: {int(val)}")
                dist_str = ", ".join(dist_parts)
                split_str = "Leaf Node"
                if len(item) > 2 and item[2] is not None:
                    split_info = item[2]
                    factor = split_info[0]
                    p_val = split_info[1]
                    split_str = f"Split on '{factor}' (p={p_val:.3e})"
                rows.append([path, dist_str, split_str])
            return rows
    except Exception as e:
        pass
    # Fallback to single text row if parsing fails
    if tree_str.strip():
        return [["Tree Summary", tree_str.strip()[:100] + "...", "—"]]
    return []

def parse_performance_report(text):
    data = {"modules_count": "0", "submodules_count": "0", "low_modules": [], "low_submodules": []}
    
    m_counts = re.search(r"Modules:\s*(\d+)\s*\|\s*Sub-Modules:\s*(\d+)", text, re.IGNORECASE)
    if m_counts:
        data["modules_count"] = m_counts.group(1)
        data["submodules_count"] = m_counts.group(2)
        
    m_sect = re.search(r"Lowest Performing Modules\s*---(.*?)(?:Lowest Performing Sub-Modules|$)", text, re.DOTALL | re.IGNORECASE)
    if m_sect:
        for line in m_sect.group(1).split('\n'):
            line_s = line.strip()
            if "Module ID" in line_s:
                m_id = re.search(r"Module ID:\s*(\w+)", line_s)
                m_val = re.search(r"Value:\s*([\d\.]+)", line_s)
                if m_id and m_val:
                    data["low_modules"].append([m_id.group(1), m_val.group(1)])
                    
    sm_sect = re.search(r"Lowest Performing Sub-Modules\s*---(.*)", text, re.DOTALL | re.IGNORECASE)
    if sm_sect:
        for line in sm_sect.group(1).split('\n'):
            line_s = line.strip()
            if "Sub-Module" in line_s:
                sm_id = re.search(r"Sub-Module:\s*(\w+)", line_s)
                sm_parent = re.search(r"Parent:\s*(\w+)", line_s)
                sm_val = re.search(r"Value:\s*([\d\.]+)", line_s)
                if sm_id and sm_val:
                    parent_val = sm_parent.group(1) if sm_parent else "—"
                    data["low_submodules"].append([sm_id.group(1), parent_val, sm_val.group(1)])
                    
    return data

def parse_multi_table_correlation_report(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    matrices = {}
    current_title = None
    current_header = None
    current_rows = []
    
    for idx, line in enumerate(lines):
        if line.startswith('='):
            continue
        if "Correlation Matrix" in line or "correlation matrix" in line:
            if current_title and current_header and current_rows:
                matrices[current_title] = (current_header, current_rows)
            current_title = line.strip()
            current_header = None
            current_rows = []
        elif line.startswith(','):
            current_header = [x.strip() for x in line.split(',')]
        else:
            if current_title:
                parts = [x.strip() for x in line.split(',')]
                if parts and parts[0]:
                    current_rows.append(parts)
                    
    if current_title and current_header and current_rows:
        matrices[current_title] = (current_header, current_rows)
        
    return matrices

def get_top_correlations_from_parsed(header, rows, top_n=10):
    correlations = []
    for row in rows:
        row_metric = row[0]
        for col_idx, val_str in enumerate(row[1:]):
            header_col_idx = col_idx + 1
            if header_col_idx >= len(header):
                continue
            col_metric = header[header_col_idx]
            if not col_metric:
                continue
            if row_metric == col_metric:
                continue
            if row_metric >= col_metric:
                continue
            try:
                val = float(val_str)
                correlations.append((row_metric, col_metric, val))
            except ValueError:
                pass
    correlations.sort(key=lambda x: abs(x[2]), reverse=True)
    return correlations[:top_n]

# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXPORTABLE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def generate_master_pdf_bytes(txt_content: str) -> bytes:
    """Compile master consolidated report text content to styled PDF bytes."""
    sections = parse_txt_content(txt_content)
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=3.2 * cm,
        bottomMargin=1.8 * cm,
        title="RISK INTELL Pipeline Automation Report",
        author="RISK INTELL Platform",
    )
    
    story = []
    usable_w = PAGE_W - 2 * MARGIN
    
    # ── COVER / TITLE PAGE ──
    # Shift title slightly to the right to account for the cover sidebar
    cover_s = get_styles()
    cover_s["title"].leftIndent = 1.0 * cm
    cover_s["subtitle"].leftIndent = 1.0 * cm
    cover_s["section_h2"].leftIndent = 1.0 * cm
    cover_s["body"].leftIndent = 1.0 * cm
    cover_s["body_bold"].leftIndent = 1.0 * cm
    
    story.append(Spacer(1, 4.0 * cm))
    story.append(Paragraph("RISK INTELL Platform", cover_s["title"]))
    story.append(Paragraph("Consolidated Master Performance & Risk Analysis Report", cover_s["subtitle"]))
    story.append(Spacer(1, 1.2 * cm))
    
    overview_text = (
        "This master report aggregates the outputs from the 9-script sequential RISK INTELL pipeline, "
        "covering performance modeling, Statistical Process Control (SPC), risk scenario forecasting "
        "via regression and PyTorch, Fourier trend repetitions, and segmentations (CHAID). It provides "
        "an enterprise-wide (L0) and module-specific (L1/L2) view of compliance and ESG performance."
    )
    
    story.append(Paragraph("Executive Overview", cover_s["section_h2"]))
    story.append(Paragraph(overview_text, cover_s["body"]))
    story.append(Spacer(1, 0.8 * cm))
    
    # Metadata card on cover
    metadata_grid = [
        [Paragraph("Document Ref:", cover_s["meta_label"]), Paragraph("RISK-INTELL-2026-CONS", cover_s["meta_value"]),
         Paragraph("Date Prepared:", cover_s["meta_label"]), Paragraph(datetime.now().strftime("%B %d, %Y"), cover_s["meta_value"])],
        [Paragraph("Report Scope:", cover_s["meta_label"]), Paragraph("L0 Enterprise + L1 Modules", cover_s["meta_value"]),
         Paragraph("Classification:", cover_s["meta_label"]), Paragraph("CONFIDENTIAL", cover_s["meta_value"])]
    ]
    meta_tbl = Table(metadata_grid, colWidths=[3.2 * cm, 4.2 * cm, 3.2 * cm, 4.2 * cm])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), SKY_PALE),
        ("BOX", (0,0), (-1,-1), 0.5, SKY_LIGHT),
        ("PADDING", (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    
    meta_tbl_wrapper = Table([[meta_tbl]], colWidths=[usable_w])
    meta_tbl_wrapper.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 1.0 * cm),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(meta_tbl_wrapper)
    story.append(PageBreak())
    
    # ── SECTION 1: PERFORMANCE & REGRESSION ANALYSIS ──
    story.append(Paragraph("1. Performance & Risk Analysis (Regression Models)", s["section_h1"]))
    story.append(Paragraph(
        "This section details the Level-1 (Module) and Level-0 (Enterprise) risk modeling results. "
        "The system runs multi-variable linear regressions and deep neural networks (PyTorch) to estimate "
        "compliance scores, identify forecasting mean-squared-errors (MSE), and simulate worst-case "
        "risk scenarios using Monte Carlo methods.", s["body"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    # Render Performance Summary Statistics on first page of content
    perf_text = sections.get("performance_report_2025.txt", "")
    if perf_text:
        perf_data = parse_performance_report(perf_text)
        story.append(Paragraph("Performance Summary Stats (2025)", s["section_h2"]))
        
        perf_grid = [
            [Paragraph("Total Modules Analyzed:", s["meta_label"]), Paragraph(f"{perf_data['modules_count']}", s["meta_value"]),
             Paragraph("Total Sub-Modules:", s["meta_label"]), Paragraph(f"{perf_data['submodules_count']}", s["meta_value"])]
        ]
        perf_tbl = Table(perf_grid, colWidths=[4.2 * cm, 2.8 * cm, 4.2 * cm, 2.8 * cm])
        perf_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), SKY_PALE),
            ("BOX", (0,0), (-1,-1), 0.5, SKY_LIGHT),
            ("PADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(perf_tbl)
        story.append(Spacer(1, 0.3 * cm))
        
        if perf_data["low_modules"]:
            low_mod_p = []
            for item in perf_data["low_modules"]:
                low_mod_p.append([item[0], Paragraph(f"<b>{item[1]}</b>", score_color_style(item[1]))])
            lmt = build_styled_table(["Lowest Modules ID", "Performance Value"], low_mod_p, col_widths=[usable_w * 0.5, usable_w * 0.5])
            story.append(Paragraph("Lowest Performing Modules:", s["body_bold"]))
            story.append(lmt)
            story.append(Spacer(1, 0.3 * cm))
            
        if perf_data["low_submodules"]:
            low_sub_p = []
            for item in perf_data["low_submodules"]:
                low_sub_p.append([item[0], item[1], Paragraph(f"<b>{item[2]}</b>", score_color_style(item[2]))])
            lst = build_styled_table(["Lowest Sub-Modules ID", "Parent Module", "Performance Value"], low_sub_p, col_widths=[usable_w * 0.4, usable_w * 0.3, usable_w * 0.3])
            story.append(Paragraph("Lowest Performing Sub-Modules (Bottom 3):", s["body_bold"]))
            story.append(lst)
            story.append(Spacer(1, 0.4 * cm))
            
    ms_text = sections.get("ESGRC_Module_model_summary.txt", "")
    if ms_text:
        ms_data = parse_model_summary(ms_text)
        story.append(Paragraph("ESGRC Module Summary (Level 1)", s["section_h2"]))
        
        meta_grid = [
            [Paragraph("Overall Risk Score:", s["meta_label"]), Paragraph(f"{ms_data['Risk']}", s["meta_value"]),
             Paragraph("Average MSE:", s["meta_label"]), Paragraph(f"{ms_data['MSE']}", s["meta_value"])],
            [Paragraph("Confidence Score:", s["meta_label"]), Paragraph(f"{ms_data['Confidence']}", s["meta_value"]),
             Paragraph("", s["meta_label"]), Paragraph("", s["meta_value"])]
        ]
        meta_tbl = Table(meta_grid, colWidths=[3.2 * cm, 3.8 * cm, 3.2 * cm, 3.8 * cm])
        meta_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), SKY_PALE),
            ("BOX", (0,0), (-1,-1), 0.5, SKY_LIGHT),
            ("PADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(meta_tbl)
        story.append(Spacer(1, 0.3 * cm))
        
        if ms_data["Scenarios"]:
            story.append(Paragraph("Risk Scenarios (L1 Module Level)", s["body_bold"]))
            tbl_rows = []
            for item in ms_data["Scenarios"]:
                sc_name, val = item[0], item[1]
                tbl_rows.append([sc_name, Paragraph(f"<b>{val}</b>", score_color_style(val))])
            sc_tbl = build_styled_table(["Scenario Name", "Risk Score"], tbl_rows, col_widths=[usable_w * 0.7, usable_w * 0.3])
            story.append(sc_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
        if ms_data["Actions"]:
            story.append(Paragraph("Recommended Follow-up Actions:", s["body_bold"]))
            act_rows = []
            for idx, act in enumerate(ms_data["Actions"]):
                act_rows.append([str(idx + 1), Paragraph(act, s["tbl_cell"])])
            act_tbl = build_styled_table(["#", "Remediation Action Item"], act_rows, col_widths=[1.0 * cm, usable_w - 1.0 * cm])
            story.append(act_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    l0_text = sections.get("L0_Risk_Analysis_Report_2025.txt", "")
    if l0_text:
        l0_data = parse_l0_risk_report(l0_text)
        story.append(Paragraph("Enterprise Risk Assessment (Level 0)", s["section_h2"]))
        
        l0_meta_grid = [
            [Paragraph("L0 Overall Risk Score:", s["meta_label"]), Paragraph(f"{l0_data['Risk']}", s["meta_value"]),
             Paragraph("L0 Average MSE:", s["meta_label"]), Paragraph(f"{l0_data['MSE']}", s["meta_value"])],
            [Paragraph("L0 Confidence Score:", s["meta_label"]), Paragraph(f"{l0_data['Confidence']}", s["meta_value"]),
             Paragraph("", s["meta_label"]), Paragraph("", s["meta_value"])]
        ]
        l0_meta_tbl = Table(l0_meta_grid, colWidths=[3.2 * cm, 3.8 * cm, 3.2 * cm, 3.8 * cm])
        l0_meta_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), SKY_PALE),
            ("BOX", (0,0), (-1,-1), 0.5, SKY_LIGHT),
            ("PADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(l0_meta_tbl)
        story.append(Spacer(1, 0.3 * cm))
        
        if l0_data["Scenarios"]:
            story.append(Paragraph("Top Risk Scenarios (L0 Enterprise Level)", s["body_bold"]))
            l0_tbl_rows = []
            for item in l0_data["Scenarios"]:
                sc_name, val = item[0], item[1]
                l0_tbl_rows.append([sc_name, Paragraph(f"<b>{val}</b>", score_color_style(val))])
            l0_sc_tbl = build_styled_table(["Scenario Name", "Risk Score"], l0_tbl_rows, col_widths=[usable_w * 0.7, usable_w * 0.3])
            story.append(l0_sc_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
        if l0_data["Metrics"]:
            story.append(Paragraph("Key Drivers in High-Risk Scenarios:", s["body_bold"]))
            driver_rows = []
            for sc, details in l0_data["Metrics"].items():
                details_p = "<br/>".join(details)
                driver_rows.append([sc, Paragraph(details_p, s["tbl_cell"])])
            driver_tbl = build_styled_table(["Scenario", "Driving Metrics / Entities"], driver_rows, col_widths=[usable_w * 0.3, usable_w * 0.7])
            story.append(driver_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
        if l0_data["Actions"]:
            story.append(Paragraph("Recommended L0 Follow-up Actions:", s["body_bold"]))
            l0_act_rows = []
            for idx, act in enumerate(l0_data["Actions"]):
                l0_act_rows.append([str(idx + 1), Paragraph(act, s["tbl_cell"])])
            l0_act_tbl = build_styled_table(["#", "Remediation Action Item"], l0_act_rows, col_widths=[1.0 * cm, usable_w - 1.0 * cm])
            story.append(l0_act_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    story.append(PageBreak())
    
    # ── SECTION 2: STATISTICAL PROCESS CONTROL (SPC) ──
    story.append(Paragraph("2. Statistical Process Control (SPC) & FMEA RPN Analysis", s["section_h1"]))
    story.append(Paragraph(
        "Statistical Process Control (SPC) defines the upper and lower control limits for module volatility. "
        "Combining this with Failure Mode and Effects Analysis (FMEA), we compute Risk Priority Numbers (RPN) "
        "to rank which metrics present the highest operational risk.", s["body"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    spcl0_text = sections.get("SPC_summary_L0_2026-07-05.txt", "")
    if spcl0_text:
        spcl0_rows = parse_tsv_table(spcl0_text)
        if spcl0_rows:
            story.append(Paragraph("Enterprise-Level SPC Statistical Parameters (L0 View)", s["section_h2"]))
            story.append(Paragraph(
                "The following table displays SPC statistical control limits and Failure Mode and Effects Analysis "
                "(FMEA) Risk Priority Numbers (RPN) aggregated for L0 modules.", s["body"]
            ))
            story.append(Spacer(1, 0.15 * cm))
            
            hdr = spcl0_rows[0]
            hdr_clean = [h.replace("_", " ").title() for h in hdr]
            data_rows = []
            for r in spcl0_rows[1:]:
                if len(r) >= 7:
                    data_rows.append([
                        r[0], r[1], r[2], r[3], r[4], 
                        Paragraph(f"<b>{r[5]}</b>", ParagraphStyle("rpn", parent=s["tbl_cell_bold"], textColor=RED if int(r[5]) > 1000 else INK_DARK)),
                        r[6]
                    ])
            spc_tbl = build_styled_table(hdr_clean, data_rows, col_widths=[2.8*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.2*cm, 2.0*cm, 4.4*cm])
            story.append(spc_tbl)
            story.append(Spacer(1, 0.5 * cm))
            
    ms_spc_text = sections.get("metrics_summary_2026-07-05.txt", "")
    if ms_spc_text:
        ms_spc_rows = parse_tsv_table(ms_spc_text)
        if ms_spc_rows and len(ms_spc_rows) > 1:
            story.append(Paragraph("Top Metric SPC Limits and RPN Scores (Bottom / High Risk)", s["section_h2"]))
            story.append(Paragraph(
                "Showing the top 15 metrics with the highest Risk Priority Number (RPN) scores. "
                "These metrics have demonstrated significant process volatility or compliance hazard.", s["body"]
            ))
            story.append(Spacer(1, 0.15 * cm))
            
            hdr = ms_spc_rows[0]
            hdr_clean = [h.replace("_", " ").title() for h in hdr]
            
            data_lines = ms_spc_rows[1:]
            try:
                data_lines.sort(key=lambda x: int(x[6]), reverse=True)
            except:
                pass
                
            top_lines = data_lines[:15]
            formatted_lines = []
            for r in top_lines:
                if len(r) >= 8:
                    formatted_lines.append([
                        r[0], r[1], r[2], r[3], r[4], r[5],
                        Paragraph(f"<b>{r[6]}</b>", ParagraphStyle("rpn2", parent=s["tbl_cell_bold"], textColor=RED if int(r[6]) > 100 else INK_DARK)),
                        r[7]
                    ])
            metrics_spc_tbl = build_styled_table(hdr_clean, formatted_lines, col_widths=[2.4*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm, 3.0*cm])
            story.append(metrics_spc_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    story.append(PageBreak())
    
    # ── SECTION 3: TRENDS, REPETITIONS & RISK SEGMENTATION ──
    story.append(Paragraph("3. Trends, Fourier Repetitions & CHAID Risk Segmentation", s["section_h1"]))
    story.append(Paragraph(
        "This section tracks directional trends (increasing, decreasing, or stable) using linear trends. "
        "We apply Fast Fourier Transforms (FFT) to detect recurring frequency cycles (repetitions) in the performance data, "
        "and construct Chi-squared Automatic Interaction Detector (CHAID) decision trees to segment risk tiers.", s["body"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    tr_l0_text = sections.get("trends_and_repetitions_report_L0.txt", "")
    tr_met_text = sections.get("trends_and_repetitions_report_esgrc.txt", "")
    
    if tr_l0_text:
        l0_tr_data = parse_trends_repetitions(tr_l0_text)
        if l0_tr_data["trends"]:
            story.append(Paragraph("Enterprise-Level Trends & Fourier Repetitions (L0 View)", s["section_h2"]))
            
            tr_rows = []
            for k in sorted(l0_tr_data["trends"].keys()):
                trend = l0_tr_data["trends"][k]
                rep = l0_tr_data["repetitions"].get(k, "Stable / No clear repetition")
                if "decreasing" in trend.lower():
                    trend_p = Paragraph(f"<font color='{RED.hexval()}'>▼ {trend}</font>", s["tbl_cell_bold"])
                elif "increasing" in trend.lower():
                    trend_p = Paragraph(f"<font color='{GREEN.hexval()}'>▲ {trend}</font>", s["tbl_cell_bold"])
                else:
                    trend_p = Paragraph(f"<font color='{AMBER.hexval()}'>► {trend}</font>", s["tbl_cell_bold"])
                    
                tr_rows.append([k, trend_p, Paragraph(rep, s["tbl_cell"])])
                
            tr_tbl = build_styled_table(["L0 Entity / Module", "Trend", "Fourier Repetition Summary"], tr_rows, col_widths=[usable_w * 0.3, usable_w * 0.25, usable_w * 0.45])
            story.append(tr_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    if tr_met_text:
        met_tr_data = parse_trends_repetitions(tr_met_text)
        if met_tr_data["trends"]:
            story.append(Paragraph("High-Risk Metric Volatility & Trends (Decreasing Bottom Metrics)", s["section_h2"]))
            story.append(Paragraph(
                "List of metrics exhibiting a decreasing trend over time. A decreasing trend for these performance metrics "
                "calls for compliance and risk corrective actions.", s["body"]
            ))
            story.append(Spacer(1, 0.15 * cm))
            
            dec_rows = []
            count = 0
            for k in sorted(met_tr_data["trends"].keys()):
                trend = met_tr_data["trends"][k]
                if "decreasing" in trend.lower():
                    rep = met_tr_data["repetitions"].get(k, "No clear repetition")
                    trend_p = Paragraph(f"<font color='{RED.hexval()}'>▼ {trend}</font>", s["tbl_cell_bold"])
                    dec_rows.append([k, trend_p, Paragraph(rep, s["tbl_cell"])])
                    count += 1
                    if count >= 15:
                        break
            if dec_rows:
                tr_tbl = build_styled_table(["Metric ID", "Trend", "Fourier Repetition Summary"], dec_rows, col_widths=[usable_w * 0.25, usable_w * 0.25, usable_w * 0.5])
                story.append(tr_tbl)
                story.append(Spacer(1, 0.4 * cm))
                
    chaid_l0_text = sections.get("chaid_risk_segmentation_L0.txt", "")
    chaid_met_text = sections.get("chaid_risk_segmentation_report_esgrc.txt", "")
    
    if chaid_l0_text:
        ch_l0_data = parse_chaid_report(chaid_l0_text)
        story.append(Paragraph("CHAID Decision-Tree Risk Segmentation (L0 Enterprise Level)", s["section_h2"]))
        
        if ch_l0_data["tree"]:
            tree_rows = parse_chaid_tree_to_rows(ch_l0_data["tree"])
            if tree_rows:
                story.append(Paragraph("CHAID L0 Decision-Tree Nodes:", s["body_bold"]))
                tree_tbl = build_styled_table(
                    ["Module Path / Node", "Risk Tier Distribution", "Split Factor / Condition"],
                    [[r[0], r[1], r[2]] for r in tree_rows],
                    col_widths=[usable_w * 0.35, usable_w * 0.3, usable_w * 0.35]
                )
                story.append(tree_tbl)
                story.append(Spacer(1, 0.3 * cm))
                
        if ch_l0_data["distribution"]:
            story.append(Paragraph("L0 Risk Level Distribution:", s["body_bold"]))
            dist_rows = []
            for r in ch_l0_data["distribution"]:
                if len(r) >= 2 and r[0].lower() != "risk_level":
                    dist_rows.append([r[0], r[1]])
            dist_tbl = build_styled_table(["Risk Tier", "Number of Modules"], dist_rows, col_widths=[usable_w * 0.5, usable_w * 0.5])
            story.append(dist_tbl)
            story.append(Spacer(1, 0.3 * cm))
            
    if chaid_met_text:
        ch_data = parse_chaid_report(chaid_met_text)
        story.append(Paragraph("CHAID Decision-Tree Risk Segmentation (Metrics Level)", s["section_h2"]))
        
        if ch_data["tree"]:
            tree_rows = parse_chaid_tree_to_rows(ch_data["tree"])
            if tree_rows:
                story.append(Paragraph("CHAID Metric Decision-Tree Nodes:", s["body_bold"]))
                tree_tbl = build_styled_table(
                    ["Metric Path / Node", "Risk Tier Distribution", "Split Factor / Condition"],
                    [[r[0], r[1], r[2]] for r in tree_rows],
                    col_widths=[usable_w * 0.35, usable_w * 0.3, usable_w * 0.35]
                )
                story.append(tree_tbl)
                story.append(Spacer(1, 0.3 * cm))

        if ch_data["distribution"]:
            story.append(Paragraph("Risk Level Distribution:", s["body_bold"]))
            dist_rows = []
            for r in ch_data["distribution"]:
                if len(r) >= 2 and r[0].lower() != "risk_level":
                    dist_rows.append([r[0], r[1]])
            dist_tbl = build_styled_table(["Risk Tier", "Number of Entities"], dist_rows, col_widths=[usable_w * 0.5, usable_w * 0.5])
            story.append(dist_tbl)
            story.append(Spacer(1, 0.3 * cm))
            
        if ch_data["high_risk_metrics"]:
            story.append(Paragraph("High-Risk/Critical Metrics Detail:", s["body_bold"]))
            hdr = ["Metric ID", "Risk Tier", "Trend", "Repetition", "Inconsistency Level"]
            metric_rows = []
            count = 0
            for r in ch_data["high_risk_metrics"]:
                if len(r) >= 5 and r[0].lower() != "metric":
                    risk = r[1]
                    risk_style = RED if "critical" in risk.lower() else AMBER
                    risk_p = Paragraph(f"<b>{risk}</b>", ParagraphStyle("risk", parent=s["tbl_cell_bold"], textColor=risk_style))
                    metric_rows.append([r[0], risk_p, r[2], r[3], r[4]])
                    count += 1
                    if count >= 12:
                        break
            ch_tbl = build_styled_table(hdr, metric_rows, col_widths=[usable_w * 0.2, usable_w * 0.2, usable_w * 0.15, usable_w * 0.25, usable_w * 0.2])
            story.append(ch_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    story.append(PageBreak())
    
    # ── SECTION 4: CORRELATION & INCONSISTENCY REPORTS ──
    story.append(Paragraph("4. Correlation & Inconsistency Analysis", s["section_h1"]))
    story.append(Paragraph(
        "Here we analyze how different modules and sub-modules move together. Strong correlations highlight "
        "structural dependencies. Inconsistencies flag metrics that should move together but diverge, indicating "
        "data quality issues or compliance conflicts.", s["body"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    corr_l0_text = sections.get("correlation_analysis_L0.txt", "")
    if corr_l0_text:
        story.append(Paragraph("Strongest L0 Module Correlations", s["section_h2"]))
        story.append(Paragraph(
            "Displays the strongest correlated pairs of L0 modules (excluding self-correlations).", s["body"]
        ))
        
        lines_l0 = [l.strip() for l in corr_l0_text.split('\n') if l.strip()]
        header_l0 = []
        rows_l0 = []
        for line in lines_l0:
            if line.startswith(','):
                header_l0 = [x.strip() for x in line.split(',')]
            elif ',' in line:
                parts = [x.strip() for x in line.split(',')]
                if parts and parts[0] and not parts[0].startswith('='):
                    rows_l0.append(parts)
                    
        if header_l0 and rows_l0:
            top_corr_l0 = get_top_correlations_from_parsed(header_l0, rows_l0, top_n=10)
            l0_corr_rows = []
            for m1, m2, val in top_corr_l0:
                l0_corr_rows.append([m1, m2, Paragraph(f"<b>{val:.4f}</b>", corr_color_style(val))])
            l0_corr_tbl = build_styled_table(["Entity A", "Entity B", "Correlation Coefficient"], l0_corr_rows, col_widths=[usable_w * 0.35, usable_w * 0.35, usable_w * 0.3])
            story.append(l0_corr_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    corr_text = sections.get("M_G_SM_correlation_report_esgrc.txt", "")
    if corr_text:
        matrices = parse_multi_table_correlation_report(corr_text)
        story.append(Paragraph("Top Volatility Correlations within ESGRC Module", s["section_h2"]))
        
        for title, (header, rows) in matrices.items():
            top_corr = get_top_correlations_from_parsed(header, rows, top_n=5)
            if top_corr:
                story.append(Paragraph(f"<b>{title} (Strongest Pairs)</b>", s["body_bold"]))
                corr_rows = []
                for m1, m2, val in top_corr:
                    corr_rows.append([m1, m2, Paragraph(f"<b>{val:.4f}</b>", corr_color_style(val))])
                corr_tbl = build_styled_table(["Entity A", "Entity B", "Correlation Coefficient"], corr_rows, col_widths=[usable_w * 0.35, usable_w * 0.35, usable_w * 0.3])
                story.append(corr_tbl)
                story.append(Spacer(1, 0.3 * cm))
                
    inc_text = sections.get("inconsistencies_report_esgrc.txt", "")
    if inc_text:
        inc_data = parse_inconsistencies(inc_text)
        story.append(Paragraph("Independent Compliance Inconsistencies (Top 12)", s["section_h2"]))
        story.append(Paragraph(
            "Pairs of metrics that exhibit diverging performance signals despite being structurally correlated.", s["body"]
        ))
        story.append(Spacer(1, 0.15 * cm))
        
        if inc_data["independent"]:
            hdr = ["Entity A", "Entity B", "Correlation", "Sample Count", "Percentage"]
            rows_formatted = []
            count = 0
            for r in inc_data["independent"]:
                if len(r) >= 5:
                    corr_val = r[2].replace("Corr=", "")
                    count_val = r[3].replace("Count=", "")
                    pct_val = r[4]
                    
                    rows_formatted.append([
                        r[0], r[1],
                        Paragraph(f"<b>{corr_val}</b>", corr_color_style(corr_val)),
                        count_val, pct_val
                    ])
                    count += 1
                    if count >= 12:
                        break
            inc_tbl = build_styled_table(hdr, rows_formatted, col_widths=[usable_w * 0.2, usable_w * 0.2, usable_w * 0.2, usable_w * 0.2, usable_w * 0.2])
            story.append(inc_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    inc_l0_text = sections.get("inconsistency_report_L0.txt", "")
    if inc_l0_text:
        inc_l0_data = parse_inconsistencies(inc_l0_text)
        if inc_l0_data["independent"]:
            story.append(Paragraph("Enterprise-Level L0 Compliance Inconsistencies (Top 10)", s["section_h2"]))
            hdr = ["L0 Entity A", "L0 Entity B", "Correlation", "Sample Count", "Percentage"]
            rows_formatted = []
            count = 0
            for r in inc_l0_data["independent"]:
                if len(r) >= 5:
                    corr_val = r[2].replace("Corr=", "")
                    count_val = r[3].replace("Count=", "")
                    pct_val = r[4]
                    
                    rows_formatted.append([
                        r[0], r[1],
                        Paragraph(f"<b>{corr_val}</b>", corr_color_style(corr_val)),
                        count_val, pct_val
                    ])
                    count += 1
                    if count >= 10:
                        break
            inc_l0_tbl = build_styled_table(hdr, rows_formatted, col_widths=[usable_w * 0.2, usable_w * 0.2, usable_w * 0.2, usable_w * 0.2, usable_w * 0.2])
            story.append(inc_l0_tbl)
            story.append(Spacer(1, 0.4 * cm))
            
    story.append(PageBreak())
    
    # ── SECTION 5: LOW-PERFORMING ENTITIES DETAIL ──
    story.append(Paragraph("5. Low-Performing Entities Detail", s["section_h1"]))
    story.append(Paragraph(
        "Detailed registry of entities classified as low-performing based on the weighted-average compliance limits. "
        "This is segmented by Metrics, Groups, and Sub-Modules to support fine-grained remediation workflows.", s["body"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    lp_text = sections.get("low_performing_entities_report_esgrc.txt", "")
    if lp_text:
        lp_tables = parse_low_performers(lp_text)
        
        lpm_data = lp_tables.get("Low-Performing Metrics", [])
        if lpm_data and len(lpm_data) > 1:
            story.append(Paragraph("Low-Performing Metrics (Bottom 10)", s["section_h2"]))
            hdr = [h.strip() for h in lpm_data[0]]
            rows = []
            for r in lpm_data[1:]:
                if len(r) >= 4:
                    sc = r[3]
                    rows.append([r[0], r[1], r[2], Paragraph(f"<b>{sc}</b>", score_color_style(sc))])
            tbl_lpm = build_styled_table(hdr, rows, col_widths=[1.5*cm, 2.8*cm, 10.3*cm, 2.8*cm])
            story.append(tbl_lpm)
            story.append(Spacer(1, 0.4 * cm))
            
        lpg_data = lp_tables.get("Low-Performing Groups", [])
        if lpg_data and len(lpg_data) > 1:
            story.append(Paragraph("Low-Performing Groups (Bottom 10)", s["section_h2"]))
            hdr = [h.strip() for h in lpg_data[0]]
            rows = []
            for r in lpg_data[1:]:
                if len(r) >= 4:
                    sc = r[3]
                    rows.append([r[0], r[1], r[2], Paragraph(f"<b>{sc}</b>", score_color_style(sc))])
            tbl_lpg = build_styled_table(hdr, rows, col_widths=[1.5*cm, 2.8*cm, 10.3*cm, 2.8*cm])
            story.append(tbl_lpg)
            story.append(Spacer(1, 0.4 * cm))
            
        lps_data = lp_tables.get("Low-Performing Sub-Modules", [])
        if lps_data and len(lps_data) > 1:
            story.append(Paragraph("Low-Performing Sub-Modules (Bottom 10)", s["section_h2"]))
            hdr = [h.strip() for h in lps_data[0]]
            rows = []
            for r in lps_data[1:]:
                if len(r) >= 4:
                    sc = r[3]
                    rows.append([r[0], r[1], r[2], Paragraph(f"<b>{sc}</b>", score_color_style(sc))])
            tbl_lps = build_styled_table(hdr, rows, col_widths=[1.5*cm, 2.8*cm, 10.3*cm, 2.8*cm])
            story.append(tbl_lps)
            story.append(Spacer(1, 0.4 * cm))
            
    # ── SECTION 6: EXECUTIVE SUMMARY & DISCLAIMERS ──
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width=usable_w, thickness=1.5, color=SKY_DARK, spaceAfter=15))
    story.append(Paragraph("Report Disclaimer", s["section_h2"]))
    story.append(Paragraph(
        "This master consolidated report was automatically generated from the outputs of the "
        "9-script sequential RISK INTELL pipeline using a weighted-average compliance model. "
        "All calculations, limits, and segmentations are based on the uploaded data files. "
        "This report is confidential and intended for authorized personnel only.",
        s["disclaimer"]
    ))
    
    # Draw cover page layout on page 1, and regular headers on page 2+
    doc.build(story, onFirstPage=draw_cover_background, onLaterPages=draw_header_footer)
    return buf.getvalue()
