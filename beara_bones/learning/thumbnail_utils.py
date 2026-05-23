"""PDF thumbnail generation using pypdfium2."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def generate_pdf_thumbnail(pdf_bytes: bytes, scale: float = 0.5) -> bytes | None:
    """Render the first page of a PDF to PNG bytes."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 not installed; skipping thumbnail generation")
        return None

    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        if len(pdf) == 0:
            return None
        page = pdf[0]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        logger.warning("Failed to generate PDF thumbnail: %s", exc)
        return None
