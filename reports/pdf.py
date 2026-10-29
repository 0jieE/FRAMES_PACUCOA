"""ReportLab PDF report builders."""
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, legal
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table as RLTable, TableStyle

from .builders import Cell

NAVY = colors.HexColor("#3b1466")  # theme purple
STATUS_FILL = {
    "COMPLIED": colors.HexColor("#d1e7dd"),
    "EXPIRING": colors.HexColor("#d1e7dd"),
    "INCOMPLETE": colors.HexColor("#fff3cd"),
    "NOT_COMPLIED": colors.HexColor("#f8d7da"),
    "NA": colors.HexColor("#e9ecef"),
    "PERCENT": colors.HexColor("#efe7fa"),
}

_styles = getSampleStyleSheet()
SCHOOL = ParagraphStyle("school", parent=_styles["Normal"], fontName="Helvetica-Bold", fontSize=13, textColor=NAVY, leading=16)
SYSTEM = ParagraphStyle("system", parent=_styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#495057"), leading=11)
TITLE = ParagraphStyle("title", parent=_styles["Heading1"], fontSize=15, textColor=NAVY, spaceBefore=6, spaceAfter=4)
HEADING = ParagraphStyle("heading", parent=_styles["Heading3"], fontSize=10.5, textColor=NAVY, spaceBefore=8, spaceAfter=4)
META = ParagraphStyle("meta", parent=_styles["Normal"], fontSize=8.5, leading=11)


def _para(value, size, bold=False, color=colors.black, align=0):
    style = ParagraphStyle(
        "cell", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, leading=size + 2, textColor=color, alignment=align
    )
    return Paragraph(escape(str(value)), style)


def _table(table, available_width):
    size = table.font_size
    widths = table.col_widths or [1] * len(table.headers)
    scale = available_width / sum(widths)
    col_widths = [w * scale for w in widths]
    compact = size < 7
    header = [_para(h, size, bold=True, color=colors.white, align=1 if compact else 0) for h in table.headers]
    data, styles = [header], []
    for r, row in enumerate(table.rows, start=1):
        out = []
        for c, value in enumerate(row):
            if isinstance(value, Cell):
                align = 1 if (compact and c > 1) or value.status == "PERCENT" else 0
                out.append(_para(value.text, size, bold=value.bold, align=align))
                if value.status in STATUS_FILL:
                    styles.append(("BACKGROUND", (c, r), (c, r), STATUS_FILL[value.status]))
            else:
                out.append(_para(value if value is not None else "", size, align=1 if (compact and c > 1) else 0))
        data.append(out)
    if not table.rows:
        data.append([_para("No records match the selected filters.", size)] + [""] * (len(table.headers) - 1))
        styles.append(("SPAN", (0, 1), (-1, 1)))
    rl = RLTable(data, colWidths=col_widths, repeatRows=1)
    base = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#adb5bd")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 if compact else 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 if compact else 4),
    ]
    if table.totals_row and table.rows:
        base.append(("LINEABOVE", (0, -1), (-1, -1), 1, NAVY))
    rl.setStyle(TableStyle(base + styles))
    return rl


def render_pdf(report):
    buffer = BytesIO()
    if report.wide:
        pagesize = landscape(legal)
    elif report.landscape:
        pagesize = landscape(A4)
    else:
        pagesize = A4
    margin = 12 * mm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=14 * mm,
        title=report.title,
        author=f"{settings.SCHOOL_NAME} — FRAMES",
    )
    width = pagesize[0] - 2 * margin

    story = [
        Paragraph(escape(settings.SCHOOL_NAME), SCHOOL),
        Paragraph(escape(f"FRAMES — {settings.SYSTEM_FULL_NAME}"), SYSTEM),
        Paragraph(escape(report.title), TITLE),
    ]
    meta_rows = [[_para("Filters", 8.5, bold=True), _para("; ".join(f"{k}: {v}" for k, v in report.filters) or "None", 8.5)]]
    meta_rows.append([_para("Generated", 8.5, bold=True), _para(f"{report.generated_at:%B %d, %Y %I:%M %p} by {report.generated_by}", 8.5)])
    meta = RLTable(meta_rows, colWidths=[28 * mm, width - 28 * mm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)]))
    story += [meta, Spacer(1, 4 * mm)]

    if report.summary:
        story.append(Paragraph("Summary", HEADING))
        summary = RLTable(
            [[_para(k, 8.5, bold=True), _para(v, 8.5)] for k, v in report.summary],
            colWidths=[60 * mm, width - 60 * mm],
        )
        summary.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ced4da")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f1fb")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(summary)

    for table in report.tables:
        story.append(Paragraph(escape(table.heading), HEADING))
        story.append(_table(table, width))
    for note in report.notes:
        story += [Spacer(1, 3 * mm), Paragraph(escape(note), META)]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6c757d"))
        canvas.drawString(margin, 7 * mm, f"{settings.SCHOOL_NAME} · FRAMES · {report.title} · Confidential")
        canvas.drawRightString(pagesize[0] - margin, 7 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_sample_document(title, faculty_name, details=()):
    """Small sample PDF used by the seeder for demo uploads."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=25 * mm, title=title)
    warn = ParagraphStyle("warn", parent=_styles["Normal"], fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#b02a37"), spaceBefore=14)
    story = [
        Paragraph(escape(settings.SCHOOL_NAME), SCHOOL),
        Paragraph("Kidapawan City, Cotabato", SYSTEM),
        Spacer(1, 10 * mm),
        Paragraph(escape(title), TITLE),
        Paragraph(f"Faculty: <b>{escape(faculty_name)}</b>", META),
    ]
    for line in details:
        story.append(Paragraph(escape(line), META))
    story.append(Paragraph("SAMPLE DOCUMENT – FOR TESTING ONLY", warn))
    doc.build(story)
    return buffer.getvalue()
