import logging
import tempfile
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)


def _register_fonts():
    """Register fonts with Cyrillic support."""
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        return "DejaVu", "DejaVuBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def generate_pdf(title: str, content: str) -> bytes:
    """Generate PDF from title + text content, return bytes."""
    normal_font, bold_font = _register_fonts()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        doc = SimpleDocTemplate(
            tmp_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontName=bold_font,
            fontSize=18,
            spaceAfter=20,
        )
        body_style = ParagraphStyle(
            "CustomBody",
            parent=styles["Normal"],
            fontName=normal_font,
            fontSize=11,
            leading=16,
        )

        story = [
            Paragraph(title, title_style),
            Spacer(1, 12),
        ]

        for line in content.split("\n"):
            line = line.strip()
            if line:
                story.append(Paragraph(line, body_style))
                story.append(Spacer(1, 6))

        doc.build(story)

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
