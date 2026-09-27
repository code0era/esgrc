"""
Render a .txt / .md pipeline output into a clean PDF (in-memory, bytes).

Used by the step-file download endpoint when as_pdf=true. Handles two shapes:
- Markdown-ish recommendations (headings, **bold**, tables, bullets)
- Raw tab-separated report data (rendered monospace so columns stay aligned)

Unicode glyphs that ReportLab's built-in fonts can't render (arrows, sub/super-
scripts, math signs) are transliterated to ASCII to avoid black boxes.
"""
import io
import re
import html

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, Preformatted)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

_UNI = {"↔": "<->", "→": "->", "←": "<-", "≥": ">=", "≤": "<=", "×": "x",
        "–": "-", "-": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
        "…": "...", "·": "-", "•": "-", "−": "-", "±": "+/-", "≈": "~",
        "≠": "!=", "°": " deg", "′": "'", " ": " ",
        "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
        "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-"}


def _sani(t: str) -> str:
    for k, v in _UNI.items():
        t = t.replace(k, v)
    return t


def _inline(t: str) -> str:
    t = html.escape(_sani(t))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', t)
    return t


def _styles():
    s = getSampleStyleSheet()
    return {
        "H1": ParagraphStyle("H1", parent=s["Title"], fontSize=18, spaceAfter=6,
                             textColor=colors.HexColor("#1a2b4a")),
        "SUB": ParagraphStyle("SUB", parent=s["Normal"], fontSize=8,
                              textColor=colors.HexColor("#6b7280"), spaceAfter=10),
        "H2": ParagraphStyle("H2", parent=s["Heading1"], fontSize=13, spaceBefore=12,
                             spaceAfter=5, textColor=colors.HexColor("#1a2b4a")),
        "H3": ParagraphStyle("H3", parent=s["Heading2"], fontSize=11, spaceBefore=9,
                             spaceAfter=4, textColor=colors.HexColor("#2a3f66")),
        "H4": ParagraphStyle("H4", parent=s["Heading3"], fontSize=10, spaceBefore=7,
                             spaceAfter=3, textColor=colors.HexColor("#374151")),
        "BODY": ParagraphStyle("BODY", parent=s["Normal"], fontSize=9.5, leading=13,
                               spaceAfter=4),
        "BUL": ParagraphStyle("BUL", parent=s["Normal"], fontSize=9.5, leading=13,
                              leftIndent=14, spaceAfter=3),
        "BUL2": ParagraphStyle("BUL2", parent=s["Normal"], fontSize=9.5, leading=13,
                               leftIndent=28, spaceAfter=3),
        "MONO": ParagraphStyle("MONO", parent=s["Code"], fontSize=7.5, leading=9),
        "CELL": ParagraphStyle("CELL", parent=s["Normal"], fontSize=8.5, leading=11),
        "CELLH": ParagraphStyle("CELLH", parent=s["Normal"], fontSize=8.5, leading=11,
                                textColor=colors.white, fontName="Helvetica-Bold"),
    }


def _is_row(s: str) -> bool:
    return s.startswith("|") and s.endswith("|")


def _cells(s: str):
    return [c.strip() for c in s.strip("|").split("|")]


def text_to_pdf(text: str, title: str) -> bytes:
    st = _styles()
    story = [Paragraph(_sani(title), st["H1"]),
             Paragraph("TBD2 pipeline output - rendered to PDF", st["SUB"]),
             HRFlowable(width="100%", thickness=1,
                        color=colors.HexColor("#2a3f66"), spaceAfter=10)]
    lines = _sani(text).replace("\r", "").split("\n")
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            story.append(Spacer(1, 4)); i += 1; continue
        # Markdown table
        if _is_row(s):
            block = []
            while i < n and _is_row(lines[i].strip()):
                block.append(_cells(lines[i].strip())); i += 1
            block = [r for r in block if not all(set(c) <= set("-: ") for c in r)]
            if block:
                data = [[Paragraph(_inline(c), st["CELLH"]) for c in block[0]]]
                for r in block[1:]:
                    data.append([Paragraph(_inline(c), st["CELL"]) for c in r])
                t = Table(data, repeatRows=1, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a3f66")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f3f5f9")]),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d2e0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(t); story.append(Spacer(1, 6))
            continue
        # Tab-separated report data -> monospace block (preserve columns)
        if "\t" in raw:
            block = []
            while i < n and "\t" in lines[i]:
                block.append(lines[i].replace("\t", "    ")); i += 1
            story.append(Preformatted("\n".join(block), st["MONO"]))
            story.append(Spacer(1, 4)); continue
        if s.startswith("#### "): story.append(Paragraph(_inline(s[5:]), st["H4"]))
        elif s.startswith("### "): story.append(Paragraph(_inline(s[4:]), st["H3"]))
        elif s.startswith("## "): story.append(Paragraph(_inline(s[3:]), st["H2"]))
        elif s.startswith("# "): story.append(Paragraph(_inline(s[2:]), st["H1"]))
        elif set(s) <= set("-*_=") and len(s) >= 3:
            story.append(HRFlowable(width="100%", thickness=0.5,
                         color=colors.HexColor("#d0d5dd"), spaceBefore=4, spaceAfter=6))
        elif raw.startswith("  - ") or raw.startswith("    - "):
            story.append(Paragraph(_inline(s[2:]), st["BUL2"], bulletText="-"))
        elif s.startswith("- "):
            story.append(Paragraph(_inline(s[2:]), st["BUL"], bulletText="-"))
        else:
            story.append(Paragraph(_inline(s), st["BODY"]))
        i += 1

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=title,
                            leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    doc.build(story)
    return buf.getvalue()
