from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 16 * mm


def _style_sheet():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=31,
            textColor=colors.HexColor("#4F46E5"),
            alignment=1,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#5B2B73"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#6B7280"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyLarge",
            parent=styles["BodyText"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#111827"),
        )
    )
    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#7C3AED"))
    canvas.roundRect(MARGIN, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH - (MARGIN * 2), 4 * mm, 2 * mm, fill=True, stroke=False)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGIN, 9 * mm, "Paola Psicope - cuadernillo psicopedagogico imprimible")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 9 * mm, str(doc.page))
    canvas.restoreState()


def _activity_card(activity, styles):
    rows = [
        [
            Paragraph(f"<b>Actividad {activity['number']}</b>", styles["SmallMuted"]),
            Paragraph(activity["difficulty"], styles["SmallMuted"]),
        ],
        [Paragraph(f"<b>{activity['title']}</b>", styles["BodyLarge"]), ""],
        [Paragraph(f"<b>Objetivo:</b> {activity['objective']}", styles["BodyText"]), ""],
        [Paragraph(f"<b>Habilidad:</b> {activity['skill']}", styles["BodyText"]), ""],
        [Paragraph(f"<b>Consigna:</b> {activity['instruction']}", styles["BodyText"]), ""],
        [Paragraph("Respuesta / desarrollo:", styles["SmallMuted"]), ""],
        ["", ""],
        ["", ""],
    ]
    table = Table(rows, colWidths=[145 * mm, 25 * mm])
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (0, 2), (1, 2)),
                ("SPAN", (0, 3), (1, 3)),
                ("SPAN", (0, 4), (1, 4)),
                ("SPAN", (0, 5), (1, 5)),
                ("SPAN", (0, 6), (1, 6)),
                ("SPAN", (0, 7), (1, 7)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3E8FF")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#F3F4F6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWHEIGHT", (0, 6), (-1, 7), 24 * mm),
            ]
        )
    )
    return table


def render_workbook_pdf(plan):
    buffer = BytesIO()
    styles = _style_sheet()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title=plan.get("title") or "Cuadernillo Paola Psicope",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="a4", frames=[frame], onPage=_header_footer)])

    story = []
    story.append(Spacer(1, 55 * mm))
    story.append(Paragraph(plan.get("title", "Cuadernillo psicopedagogico"), styles["CoverTitle"]))
    story.append(Paragraph(plan.get("profile", "Material imprimible A4"), styles["BodyLarge"]))
    story.append(Spacer(1, 10 * mm))
    story.append(
        Table(
            [
                ["Tema", plan.get("topic", "")],
                ["Edad", plan.get("age", "")],
                ["Dificultad", plan.get("difficulty", "")],
                ["Hojas", str(plan.get("totalPages", ""))],
            ],
            colWidths=[35 * mm, 105 * mm],
            style=[
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2FF")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4338CA")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Como usar este cuadernillo", styles["SectionTitle"]))
    for note in plan.get("productionNotes", []):
        story.append(Paragraph(f"- {note}", styles["BodyLarge"]))
        story.append(Spacer(1, 3 * mm))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Indice visual", styles["SectionTitle"]))
    for item in plan.get("structure", []):
        story.append(Paragraph(f"{item['section']} - {item['pages']} hoja(s)", styles["BodyLarge"]))
    story.append(PageBreak())

    story.append(Paragraph("Objetivos psicopedagogicos", styles["SectionTitle"]))
    story.append(
        Paragraph(
            (
                "Este material organiza actividades graduadas para trabajar habilidades cognitivas, "
                "metacognitivas y de autorregulacion segun el perfil indicado."
            ),
            styles["BodyLarge"],
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Brief: {plan.get('brief', '')}", styles["BodyLarge"]))
    story.append(PageBreak())

    for activity in plan.get("activities", []):
        story.append(_activity_card(activity, styles))
        story.append(PageBreak())

    story.append(Paragraph("Registro de avances", styles["SectionTitle"]))
    progress_rows = [["Fecha", "Actividad", "Logro", "Observaciones"]]
    progress_rows.extend([["", "", "", ""] for _ in range(12)])
    progress = Table(progress_rows, colWidths=[30 * mm, 38 * mm, 45 * mm, 58 * mm])
    progress.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3E8FF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("ROWHEIGHT", (0, 1), (-1, -1), 13 * mm),
            ]
        )
    )
    story.append(progress)
    story.append(PageBreak())

    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("Certificado de participacion", styles["CoverTitle"]))
    story.append(
        Paragraph(
            "Se certifica que completo este recorrido de actividades con compromiso, practica y constancia.",
            styles["BodyLarge"],
        )
    )
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("Nombre: ________________________________", styles["BodyLarge"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Fecha: _________________________________", styles["BodyLarge"]))

    doc.build(story)
    return buffer.getvalue()
