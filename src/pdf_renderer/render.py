"""Turn a validated export payload into a PDF with ReportLab.

Every string in the payload is user input. It reaches ReportLab's paragraph parser only after
XML escaping, so markup in a title or description is printed as text and never interpreted (M-01,
the injection path of CVE-2023-33733). Header and footer mark each page with the exporting person
and the time (M-08).
"""

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


class PayloadError(ValueError):
    """The request does not match the expected structure."""


# Maximum lengths per text field; anything longer is rejected, not truncated
META_FIELDS = {"exported_by": 200, "exported_at": 32, "filter": 500}
TEXT_FIELDS = {
    "id": 64,
    "title": 200,
    "description": 10_000,
    "category": 64,
    "status": 64,
    "goals": 128,
    "origin": 128,
    "level": 32,
    "assets": 4_000,
    "created_at": 32,
}
NUMBER_FIELDS = ("probability", "impact", "score")
MAX_RISKS = 2_000

FIELD_LABELS = (
    ("id", "Kennung"),
    ("category", "Kategorie"),
    ("status", "Status"),
    ("goals", "Schutzziele"),
    ("origin", "Ursprung"),
    ("assets", "Betroffene Assets"),
    ("created_at", "Erfasst am"),
)


def _check_text(container: dict[str, Any], name: str, limit: int, *, required: bool) -> str:
    value = container.get(name)
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise PayloadError(f"invalid field {name!r}")
    return value


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PayloadError("payload must be an object")
    clean: dict[str, Any] = {
        name: _check_text(payload, name, limit, required=True)
        for name, limit in META_FIELDS.items()
    }
    risks = payload.get("risks")
    if not isinstance(risks, list) or len(risks) > MAX_RISKS:
        raise PayloadError("risks must be a list")
    clean["risks"] = []
    for risk in risks:
        if not isinstance(risk, dict):
            raise PayloadError("each risk must be an object")
        row: dict[str, Any] = {
            name: _check_text(risk, name, limit, required=name in ("id", "title"))
            for name, limit in TEXT_FIELDS.items()
        }
        for name in NUMBER_FIELDS:
            value = risk.get(name)
            if value is not None and (type(value) is not int or not 0 < value <= 25):
                raise PayloadError(f"invalid field {name!r}")
            row[name] = value
        clean["risks"].append(row)
    return clean


def text(value: str) -> str:
    """User text for a Paragraph: escaped first, then our own line breaks."""
    return escape(value).replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12
    )
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16
        ),
        "risk": ParagraphStyle(
            "risk", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=11
        ),
        "body": body,
        "label": ParagraphStyle("label", parent=body, textColor=colors.HexColor("#4a5568")),
    }


def _risk_block(risk: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Flowable:
    score = "nicht bewertet"
    if risk["score"] is not None:
        score = f"{risk['probability']} × {risk['impact']} = {risk['score']} ({risk['level']})"
    rows = [[Paragraph("Risikowert", styles["label"]), Paragraph(text(score), styles["body"])]]
    rows += [
        [Paragraph(label, styles["label"]), Paragraph(text(risk[key] or "–"), styles["body"])]
        for key, label in FIELD_LABELS
    ]
    rows.append(
        [
            Paragraph("Beschreibung", styles["label"]),
            Paragraph(text(risk["description"] or "–"), styles["body"]),
        ]
    )
    table = Table(rows, colWidths=[45 * mm, None])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#cbd5e0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return KeepTogether([Paragraph(text(risk["title"]), styles["risk"]), table, Spacer(1, 6 * mm)])


def render(payload: Any) -> bytes:
    data = validate(payload)
    marking = f"Exportiert von {data['exported_by']} am {data['exported_at']}"
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 15 * mm

    def decorate(canvas: Canvas, doc: BaseDocTemplate) -> None:
        # drawString prints plain text; no markup is parsed here
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4a5568"))
        canvas.drawString(margin, page_height - 10 * mm, marking)
        canvas.drawRightString(
            page_width - margin, page_height - 10 * mm, f"Filter: {data['filter']}"
        )
        canvas.drawString(margin, 8 * mm, marking)
        canvas.drawRightString(page_width - margin, 8 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        buffer,
        pagesize=(page_width, page_height),
        title="Risikoexport",
        author=data["exported_by"],
        subject=f"Filter: {data['filter']}",
        creator="IS-Risk Classifier",
    )
    frame = Frame(margin, 15 * mm, page_width - 2 * margin, page_height - 32 * mm, id="content")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=decorate)])

    styles = _styles()
    story: list[Flowable] = [
        Paragraph("Risikoexport", styles["title"]),
        Paragraph(text(f"Filter: {data['filter']} · {len(data['risks'])} Risiken"), styles["body"]),
        Spacer(1, 6 * mm),
    ]
    story += [_risk_block(risk, styles) for risk in data["risks"]]
    if not data["risks"]:
        story.append(Paragraph("Keine Risiken für diesen Filter.", styles["body"]))
    doc.build(story)
    return buffer.getvalue()
