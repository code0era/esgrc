"""
ESGRC PDF Report Generator
Produces a professional, branded A4 PDF from the ESGRC performance context dict.
Uses ReportLab (pure Python, no external binaries required).
"""

from io import BytesIO
from datetime import datetime
from typing import Dict, List, Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR PALETTE  (sky blue + white brand)
# ─────────────────────────────────────────────────────────────────────────────
SKY_DARK   = colors.HexColor("#0284C7")   # header bg, table header
SKY_MID    = colors.HexColor("#0EA5E9")   # accent, score box
SKY_LIGHT  = colors.HexColor("#BAE6FD")   # borders, alt row
SKY_PALE   = colors.HexColor("#F0F9FF")   # section bg, alt rows
INK_DARK   = colors.HexColor("#0C4A6E")   # headings, dark text
INK_GRAY   = colors.HexColor("#475569")   # body text, captions
WHITE      = colors.white
GREEN      = colors.HexColor("#10B981")
AMBER      = colors.HexColor("#F59E0B")
RED        = colors.HexColor("#EF4444")
LIGHT_GRAY = colors.HexColor("#F8FAFC")
ROW_ALT    = colors.HexColor("#E0F2FE")   # alternate table row

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm


# ─────────────────────────────────────────────────────────────────────────────
# PARAGRAPH STYLES
# ─────────────────────────────────────────────────────────────────────────────
def _styles():
    return {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#BAE6FD"),
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=INK_DARK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=INK_GRAY,
            spaceAfter=4,
            leading=14,
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName="Helvetica",
            fontSize=8,
            textColor=INK_GRAY,
        ),
        "score_label": ParagraphStyle(
            "score_label",
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#BAE6FD"),
        ),
        "score_value": ParagraphStyle(
            "score_value",
            fontName="Helvetica-Bold",
            fontSize=36,
            textColor=WHITE,
        ),
        "score_status": ParagraphStyle(
            "score_status",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=WHITE,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=7,
            textColor=INK_GRAY,
            alignment=TA_CENTER,
        ),
        "tbl_header": ParagraphStyle(
            "tbl_header",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=WHITE,
        ),
        "tbl_cell": ParagraphStyle(
            "tbl_cell",
            fontName="Helvetica",
            fontSize=8,
            textColor=INK_DARK,
            leading=11,
        ),
        "tbl_id": ParagraphStyle(
            "tbl_id",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=SKY_DARK,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCORE COLOUR HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _score_color(v: float) -> colors.Color:
    if v >= 85: return GREEN
    if v >= 75: return AMBER
    return RED

def _score_status(v: float) -> str:
    if v >= 85: return "Good Performance"
    if v >= 75: return "Moderate — Improvement Recommended"
    return "Needs Immediate Attention"


# ─────────────────────────────────────────────────────────────────────────────
# HEADER  (drawn on every page)
# ─────────────────────────────────────────────────────────────────────────────
def _draw_header(canvas, doc):
    canvas.saveState()
    # Background banner
    canvas.setFillColor(SKY_DARK)
    canvas.rect(0, PAGE_H - 2.8 * cm, PAGE_W, 2.8 * cm, fill=1, stroke=0)
    # Accent stripe
    canvas.setFillColor(SKY_MID)
    canvas.rect(0, PAGE_H - 2.95 * cm, PAGE_W, 0.15 * cm, fill=1, stroke=0)

    # Title
    canvas.setFont("Helvetica-Bold", 16)
    canvas.setFillColor(WHITE)
    canvas.drawString(MARGIN, PAGE_H - 1.5 * cm, "🛡  ESGRC Intelligence Platform")

    # Subtitle
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#BAE6FD"))
    canvas.drawString(MARGIN, PAGE_H - 2.1 * cm, "Enterprise ESG · Risk · Compliance — Low-Performing Entity Report")

    # Page number (top right)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#BAE6FD"))
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.8 * cm, f"Page {doc.page}")

    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
def _draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(SKY_LIGHT)
    canvas.rect(0, 0, PAGE_W, 1.1 * cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(INK_GRAY)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    canvas.drawString(MARGIN, 0.4 * cm, f"Generated: {ts}  |  ESGRC Intelligence Platform  |  Confidential")
    canvas.drawRightString(PAGE_W - MARGIN, 0.4 * cm, "© ESGRC Intelligence")
    canvas.restoreState()


def _draw_header_footer(canvas, doc):
    _draw_header(canvas, doc)
    _draw_footer(canvas, doc)


# ─────────────────────────────────────────────────────────────────────────────
# TABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def _build_data_table(rows: List[Dict], id_key: str, name_key: str, s: dict) -> Table:
    """Build a styled ReportLab Table from a list of dicts."""
    col_widths = [1.0 * cm, 3.2 * cm, 9.0 * cm, 2.2 * cm]

    header_row = [
        Paragraph("#",         s["tbl_header"]),
        Paragraph("ID",        s["tbl_header"]),
        Paragraph("Name",      s["tbl_header"]),
        Paragraph("Score",     s["tbl_header"]),
    ]
    data = [header_row]
    for i, row in enumerate(rows, 1):
        sc = row.get("score", 0.0)
        sc_color = _score_color(sc)
        data.append([
            Paragraph(str(i),                    s["tbl_cell"]),
            Paragraph(row.get("id", ""),         s["tbl_id"]),
            Paragraph(row.get("name", ""),       s["tbl_cell"]),
            Paragraph(f"<b>{sc:.2f}</b>",        ParagraphStyle(
                "sc", fontName="Helvetica-Bold", fontSize=8,
                textColor=sc_color,
            )),
        ])

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        # Header
        ("BACKGROUND",  (0, 0), (-1, 0), SKY_DARK),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("TOPPADDING",  (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING",(0,0), (-1, 0), 6),
        # Alternating rows
        *[
            ("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 0 else WHITE)
            for r in range(1, len(data))
        ],
        # Grid
        ("GRID",        (0, 0), (-1, -1), 0.4, SKY_LIGHT),
        ("ROWBACKGROUND",(0, 1), (-1, -1), [WHITE, ROW_ALT]),
        # Padding
        ("TOPPADDING",  (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING",(0,1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        # Borders
        ("LINEBELOW",   (0, 0), (-1, 0), 1.2, SKY_MID),
        ("LINEBELOW",   (0, -1),(-1,-1), 0.8, SKY_LIGHT),
        ("BOX",         (0, 0), (-1, -1), 0.8, SKY_LIGHT),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])
    tbl.setStyle(style)
    return tbl


# ─────────────────────────────────────────────────────────────────────────────
# MAIN  generate_pdf()
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf(context: dict) -> bytes:
    """
    Build a professional A4 PDF report from the ESGRC context dict.
    Returns raw PDF bytes ready for st.download_button().
    """
    buf    = BytesIO()
    s      = _styles()
    usable = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=3.4 * cm,     # space for header banner
        bottomMargin=1.8 * cm,  # space for footer
        title="ESGRC Performance Report",
        author="ESGRC Intelligence Platform",
    )

    story = []
    now   = datetime.now().strftime("%B %d, %Y  at  %H:%M")
    score = context.get("overall_score", 0.0)
    sc_col= _score_color(score)

    # ── Module info bar ────────────────────────────────────────────────────
    info_data = [[
        Paragraph(
            f"<b>{context.get('module_name', context.get('module_id', '—'))}</b>",
            ParagraphStyle("mn", fontName="Helvetica-Bold", fontSize=11, textColor=INK_DARK),
        ),
        Paragraph(
            f"Module ID: <b>{context.get('module_id','—')}</b>",
            ParagraphStyle("mid", fontName="Helvetica", fontSize=8, textColor=INK_GRAY, alignment=TA_RIGHT),
        ),
    ]]
    info_tbl = Table(info_data, colWidths=[usable * 0.65, usable * 0.35])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SKY_PALE),
        ("BOX",        (0, 0), (-1, -1), 0.8, SKY_LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ("LEFTPADDING",(0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0,0), (-1, -1), 10),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.4 * cm))

    # ── Overall score hero ─────────────────────────────────────────────────
    score_data = [[
        # Left: label + number
        Table(
            [[
                Paragraph("OVERALL MODULE SCORE", s["score_label"]),
            ], [
                Paragraph(f"{score:.1f} / 100", ParagraphStyle(
                    "snum", fontName="Helvetica-Bold", fontSize=32,
                    textColor=WHITE, leading=36,
                )),
            ], [
                Paragraph(_score_status(score), s["score_status"]),
            ]],
            colWidths=[usable * 0.55],
            style=TableStyle([
                ("TOPPADDING",    (0,0),(-1,-1), 4),
                ("BOTTOMPADDING",(0,0),(-1,-1), 3),
            ]),
        ),
        # Right: stat pills
        Table(
            [
                [Paragraph("Metrics",     s["score_label"]),
                 Paragraph("Groups",      s["score_label"]),
                 Paragraph("Sub-Modules", s["score_label"])],
                [
                    Paragraph(f"<b>{context.get('total_metrics',0)}</b>",
                              ParagraphStyle("sp", fontName="Helvetica-Bold", fontSize=18, textColor=WHITE)),
                    Paragraph(f"<b>{context.get('total_groups',0)}</b>",
                              ParagraphStyle("sp", fontName="Helvetica-Bold", fontSize=18, textColor=WHITE)),
                    Paragraph(f"<b>{context.get('total_sub_modules',0)}</b>",
                              ParagraphStyle("sp", fontName="Helvetica-Bold", fontSize=18, textColor=WHITE)),
                ],
            ],
            colWidths=[usable * 0.13] * 3,
            style=TableStyle([
                ("ALIGN",        (0,0),(-1,-1), "CENTER"),
                ("TOPPADDING",  (0,0),(-1,-1), 6),
                ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ]),
        ),
    ]]
    hero = Table(score_data, colWidths=[usable * 0.58, usable * 0.42])
    hero.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), SKY_MID),
        ("BOX",         (0, 0), (-1, -1), 0, WHITE),
        ("TOPPADDING",  (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0,0),(-1,-1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",(0, 0),(-1,-1), 16),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(hero)
    story.append(Spacer(1, 0.5 * cm))

    # ── Report date line ───────────────────────────────────────────────────
    story.append(Paragraph(f"Report generated on {now}   |   Analysis: Low-Performing Entity Report", s["caption"]))
    story.append(HRFlowable(width=usable, thickness=1.2, color=SKY_LIGHT, spaceAfter=14))

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 1: Low-Performing Metrics
    # ─────────────────────────────────────────────────────────────────────
    story.append(Paragraph("1.  Low-Performing Metrics  (Bottom 10)", s["section"]))
    story.append(Paragraph(
        "The following metrics recorded the lowest weighted-average scores across all data rows. "
        "These represent the most critical areas requiring immediate ESG performance intervention.",
        s["body"],
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_build_data_table(context.get("low_metrics", []), "id", "name", s))
    story.append(Spacer(1, 0.5 * cm))

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 2: Low-Performing Groups
    # ─────────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=usable, thickness=0.8, color=SKY_LIGHT, spaceAfter=6))
    story.append(Paragraph("2.  Low-Performing Groups  (Bottom 10)", s["section"]))
    story.append(Paragraph(
        "Groups are collections of related metrics. The groups below have the lowest aggregated "
        "scores and highlight which governance, risk, or compliance areas need structural improvement.",
        s["body"],
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_build_data_table(context.get("low_groups", []), "id", "name", s))
    story.append(Spacer(1, 0.5 * cm))

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 3: Low-Performing Sub-Modules
    # ─────────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=usable, thickness=0.8, color=SKY_LIGHT, spaceAfter=6))
    story.append(Paragraph("3.  Low-Performing Sub-Modules  (Bottom 10)", s["section"]))
    story.append(Paragraph(
        "Sub-modules represent broad functional units. Their scores are weighted averages "
        "across all constituent groups and metrics. Low sub-module scores indicate systemic "
        "gaps that affect multiple metrics simultaneously.",
        s["body"],
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_build_data_table(context.get("low_sub_modules", []), "id", "name", s))
    story.append(Spacer(1, 0.5 * cm))

    # ─────────────────────────────────────────────────────────────────────
    # SECTION 4: AI Executive Summary
    # ─────────────────────────────────────────────────────────────────────
    if "ai_summary" in context:
        story.append(HRFlowable(width=usable, thickness=0.8, color=SKY_LIGHT, spaceAfter=6))
        story.append(Paragraph("4.  AI Executive Summary", s["section"]))
        for paragraph in context["ai_summary"].split('\n'):
            if paragraph.strip():
                story.append(Paragraph(paragraph.strip(), s["body"]))
        story.append(Spacer(1, 0.5 * cm))

    # ─────────────────────────────────────────────────────────────────────
    # SUMMARY BOX
    # ─────────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=usable, thickness=1.2, color=SKY_MID, spaceAfter=8))
    summary_data = [[
        Paragraph("Module",       s["caption"]),
        Paragraph("Score",        s["caption"]),
        Paragraph("Status",       s["caption"]),
        Paragraph("Total Metrics",s["caption"]),
        Paragraph("Groups",       s["caption"]),
        Paragraph("Sub-Modules",  s["caption"]),
    ],[
        Paragraph(f"<b>{context.get('module_id','—')}</b>",
                  ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=9, textColor=INK_DARK)),
        Paragraph(f"<b>{score:.1f}</b>",
                  ParagraphStyle("sv2", fontName="Helvetica-Bold", fontSize=9, textColor=sc_col)),
        Paragraph(_score_status(score),
                  ParagraphStyle("sv3", fontName="Helvetica", fontSize=8, textColor=INK_GRAY)),
        Paragraph(str(context.get("total_metrics",0)),
                  ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=9, textColor=INK_DARK)),
        Paragraph(str(context.get("total_groups",0)),
                  ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=9, textColor=INK_DARK)),
        Paragraph(str(context.get("total_sub_modules",0)),
                  ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=9, textColor=INK_DARK)),
    ]]
    sum_tbl = Table(summary_data, colWidths=[usable / 6] * 6)
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), SKY_PALE),
        ("BACKGROUND",   (0, 1), (-1, 1), WHITE),
        ("BOX",          (0, 0), (-1, -1), 0.8, SKY_LIGHT),
        ("GRID",         (0, 0), (-1, -1), 0.4, SKY_LIGHT),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sum_tbl)

    # ─────────────────────────────────────────────────────────────────────
    # DISCLAIMER
    # ─────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "This report was automatically generated by the ESGRC Intelligence Platform using a "
        "weighted-average performance model. Scores are based on the uploaded metric CSV and "
        "configuration JSON. This document is confidential and intended for authorised users only.",
        ParagraphStyle("disc", fontName="Helvetica-Oblique", fontSize=7.5, textColor=INK_GRAY,
                       leading=11, borderPad=6, borderColor=SKY_LIGHT, borderWidth=0.5,
                       backColor=SKY_PALE),
    ))

    # ── Build PDF ──────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)
    return buf.getvalue()
