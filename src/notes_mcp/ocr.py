"""Tesseract OCR for printed text and screenshots."""

from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from notes_mcp.config import DEFAULT_OCR_LANG, MAX_OCR_CHARS


class OcrError(RuntimeError):
    pass


def _preprocess(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return ImageOps.autocontrast(gray)


def extract_text(image_path: str, lang: str = DEFAULT_OCR_LANG) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise OcrError(f"Image not found for OCR: {image_path}")
    try:
        with Image.open(path) as img:
            prepared = _preprocess(img.convert("RGB"))
            text = pytesseract.image_to_string(prepared, lang=lang)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract is not available on this machine. "
            "OCR runs in Docker only — start the stack: make up"
        ) from exc
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc

    text = text.strip()
    if len(text) > MAX_OCR_CHARS:
        text = text[:MAX_OCR_CHARS]
    return text
