from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
DEFAULT_TESSERACT_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def extract_image_text(path: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("OCR support requires Pillow and pytesseract. Install requirements and Tesseract OCR.") from exc

    try:
        if DEFAULT_TESSERACT_PATH.exists():
            pytesseract.pytesseract.tesseract_cmd = str(DEFAULT_TESSERACT_PATH)
        with Image.open(path) as image:
            return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR is not installed or not available on PATH.") from exc
