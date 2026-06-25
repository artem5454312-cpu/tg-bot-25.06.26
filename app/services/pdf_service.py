import logging
import tempfile
import os
import requests

logger = logging.getLogger(__name__)

FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
FONT_BOLD_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf"
FONT_PATH = "/tmp/DejaVuSans.ttf"
FONT_BOLD_PATH = "/tmp/DejaVuSans-Bold.ttf"


def _download_font(url, path):
    if not os.path.exists(path):
        try:
            r = requests.get(url, timeout=10)
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception as e:
            logger.warning(f"Font download failed: {e}")
            return False
    return True


def _register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Try system paths first
    system_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    system_bold_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]

    normal_path = None
    bold_path = None

    for p in system_paths:
        if os.path.exists(p):
            normal_path = p
            break
    for p in system_bold_paths:
        if os.path.exists(p):
            bold_path = p
            break

    # Download if not found
    if not normal_path:
        if _download_font(FONT_URL, FONT_PATH):
            normal_path = FONT_PATH
    if not bold_path:
        if _download_font(FONT_BOLD_URL, FONT_BOLD_PATH):
            bold_path = FONT_BOLD_PATH

    if normal_path and bold_path:
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", normal_path))
            pdfmetrics.registerFont(TTFont("DejaVuBold", bold_path))
            return "DejaVu", "DejaVuBold"
        except Exception as e:
            logger.warning(f"Font registration failed: {e}")

    return "Helvetica", "Helvetica-Bold"


def generate_pdf(title: str, content: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    normal_font, bold_font = _register_fonts()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        doc = SimpleDocTemplate(
            tmp_path,
            pagesize=A4,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2.5 * cm,
        )

        title_style = ParagraphStyle(
            "Title",
            fontName=bold_font,
            fontSize=20,
            spaceAfter=24,
            leading=26,
        )
        heading_style = ParagraphStyle(
            "Heading",
            fontName=bold_font,
            fontSize=14,
            spaceAfter=10,
            spaceBefore=16,
            leading=18,
        )
        body_style = ParagraphStyle(
            "Body",
            fontName=normal_font,
            fontSize=11,
            leading=17,
            spaceAfter=6,
        )

        story = [Paragraph(title, title_style), Spacer(1, 8)]

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 8))
                continue
            # Detect headings (lines ending with : or all caps short lines)
            if line.endswith(":") and len(line) < 60:
                story.append(Paragraph(line, heading_style))
            else:
                # Clean markdown artifacts
                line = line.lstrip("•-–— ")
                story.append(Paragraph(line, body_style))

        doc.build(story)

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
