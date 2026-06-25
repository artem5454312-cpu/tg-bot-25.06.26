import logging
import tempfile
import os
import urllib.request

logger = logging.getLogger(__name__)

FONT_DIR = "/tmp/fonts"
FONT_NORMAL = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

FONT_URLS = [
    (FONT_NORMAL, "https://github.com/dejavu-fonts/dejavu-fonts/raw/main/ttf/DejaVuSans.ttf"),
    (FONT_BOLD, "https://github.com/dejavu-fonts/dejavu-fonts/raw/main/ttf/DejaVuSans-Bold.ttf"),
]

SYSTEM_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
]
SYSTEM_BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
]


def _find_system_font(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _ensure_fonts():
    os.makedirs(FONT_DIR, exist_ok=True)
    for path, url in FONT_URLS:
        if not os.path.exists(path):
            try:
                logger.info(f"Downloading font from {url}")
                urllib.request.urlretrieve(url, path)
                logger.info(f"Font saved: {path}")
            except Exception as e:
                logger.warning(f"Font download failed: {e}")


def _register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Try system fonts first
    normal = _find_system_font(SYSTEM_FONT_PATHS)
    bold = _find_system_font(SYSTEM_BOLD_PATHS)

    # Try downloaded fonts
    if not normal or not bold:
        _ensure_fonts()
        if os.path.exists(FONT_NORMAL):
            normal = FONT_NORMAL
        if os.path.exists(FONT_BOLD):
            bold = FONT_BOLD

    if normal and bold:
        try:
            pdfmetrics.registerFont(TTFont("CyrFont", normal))
            pdfmetrics.registerFont(TTFont("CyrFontBold", bold))
            logger.info(f"Fonts registered: {normal}")
            return "CyrFont", "CyrFontBold"
        except Exception as e:
            logger.error(f"Font registration failed: {e}")

    logger.warning("Using Helvetica (no Cyrillic support)")
    return "Helvetica", "Helvetica-Bold"


def generate_pdf(title: str, content: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
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
            "Title", fontName=bold_font, fontSize=20,
            spaceAfter=24, leading=26,
        )
        heading_style = ParagraphStyle(
            "Heading", fontName=bold_font, fontSize=13,
            spaceAfter=8, spaceBefore=14, leading=17,
        )
        body_style = ParagraphStyle(
            "Body", fontName=normal_font, fontSize=11,
            leading=17, spaceAfter=5,
        )

        story = [Paragraph(title, title_style), Spacer(1, 8)]

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
                continue
            if line.endswith(":") and len(line) < 60:
                story.append(Paragraph(line, heading_style))
            else:
                line = line.lstrip("•-–— #*")
                story.append(Paragraph(line, body_style))

        doc.build(story)

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
