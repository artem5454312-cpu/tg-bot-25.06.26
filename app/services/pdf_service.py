import logging
import tempfile
import os

logger = logging.getLogger(__name__)


def generate_pdf(title: str, content: str) -> bytes:
    """Generate PDF via WeasyPrint (HTML→PDF, full Cyrillic support)."""
    try:
        return _generate_weasyprint(title, content)
    except Exception as e:
        logger.warning(f"WeasyPrint failed: {e}, trying reportlab")
        return _generate_reportlab(title, content)


def _generate_weasyprint(title: str, content: str) -> bytes:
    from weasyprint import HTML

    # Convert content to HTML paragraphs
    paragraphs = ""
    for line in content.split("\n"):
        line = line.strip().lstrip("•-–— #*")
        if not line:
            continue
        if line.endswith(":") and len(line) < 60:
            paragraphs += f"<h2>{line}</h2>\n"
        else:
            paragraphs += f"<p>{line}</p>\n"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
  body {{ font-family: 'Roboto', 'Arial', sans-serif; margin: 40px; color: #222; }}
  h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 20px; color: #111; }}
  h2 {{ font-size: 16px; font-weight: 700; margin-top: 20px; margin-bottom: 8px; color: #333; }}
  p {{ font-size: 13px; line-height: 1.6; margin: 4px 0; }}
</style>
</head>
<body>
<h1>{title}</h1>
{paragraphs}
</body>
</html>"""

    return HTML(string=html).write_pdf()


def _generate_reportlab(title: str, content: str) -> bytes:
    """Fallback: reportlab with downloaded font."""
    import urllib.request
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = "/tmp/DejaVuSans.ttf"
    font_bold_path = "/tmp/DejaVuSans-Bold.ttf"

    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(
                "https://github.com/dejavu-fonts/dejavu-fonts/raw/main/ttf/DejaVuSans.ttf",
                font_path
            )
        except Exception:
            pass

    if not os.path.exists(font_bold_path):
        try:
            urllib.request.urlretrieve(
                "https://github.com/dejavu-fonts/dejavu-fonts/raw/main/ttf/DejaVuSans-Bold.ttf",
                font_bold_path
            )
        except Exception:
            pass

    if os.path.exists(font_path) and os.path.exists(font_bold_path):
        pdfmetrics.registerFont(TTFont("CyrFont", font_path))
        pdfmetrics.registerFont(TTFont("CyrFontBold", font_bold_path))
        nf, bf = "CyrFont", "CyrFontBold"
    else:
        nf, bf = "Helvetica", "Helvetica-Bold"

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        doc = SimpleDocTemplate(tmp_path, pagesize=A4,
                                leftMargin=2.5*cm, rightMargin=2.5*cm,
                                topMargin=2.5*cm, bottomMargin=2.5*cm)
        title_style = ParagraphStyle("T", fontName=bf, fontSize=20, spaceAfter=24, leading=26)
        heading_style = ParagraphStyle("H", fontName=bf, fontSize=13, spaceAfter=8, spaceBefore=14)
        body_style = ParagraphStyle("B", fontName=nf, fontSize=11, leading=17, spaceAfter=5)

        story = [Paragraph(title, title_style), Spacer(1, 8)]
        for line in content.split("\n"):
            line = line.strip().lstrip("•-–— #*")
            if not line:
                story.append(Spacer(1, 6))
            elif line.endswith(":") and len(line) < 60:
                story.append(Paragraph(line, heading_style))
            else:
                story.append(Paragraph(line, body_style))

        doc.build(story)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
