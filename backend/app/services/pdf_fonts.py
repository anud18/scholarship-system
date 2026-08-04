"""Shared CJK font registration for reportlab PDF generation.

Several services render PDFs containing Traditional Chinese text (the export
package's per-student summaries and the college ranking export). reportlab needs
a CJK-capable TrueType font registered once per process. This leaf module owns
that registration so every PDF producer shares one font and one constant —
without importing each other (which would create an import cycle between
``export_package_service`` and ``college_ranking_export_service``).
"""

from __future__ import annotations

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# WenQuanYi Zen Hei ships in the backend image (fonts-wqy-zenhei).
CJK_FONT_NAME = "WQY"
CJK_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

_font_registered = False


def ensure_cjk_font() -> None:
    """Idempotently register the WQY CJK font for reportlab.

    Safe to call from every PDF entry point; the first call registers the font
    and subsequent calls are no-ops.
    """
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(TTFont(CJK_FONT_NAME, CJK_FONT_PATH, subfontIndex=0))
        _font_registered = True
