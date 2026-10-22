"""OCR for photos and scanned PDFs, via the tesseract and poppler command-line tools.

    brew install tesseract tesseract-lang poppler

English, Arabic and Malayalam are read together ("eng+ara+mal"), so a bilingual bill is one
pass. HEIC (iPhone photos) is converted with macOS `sips` first.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp"}
LANGS = "eng+ara+mal"


class OCRUnavailable(RuntimeError):
    pass


def _need(tool: str) -> str:
    found = shutil.which(tool)
    if not found:
        raise OCRUnavailable(
            f"'{tool}' is not installed. Run: brew install tesseract tesseract-lang poppler"
        )
    return found


def _tesseract(image: Path) -> str:
    out = subprocess.run(
        [_need("tesseract"), str(image), "stdout", "-l", LANGS],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        raise RuntimeError(f"tesseract failed: {out.stderr.strip()[:200]}")
    return out.stdout


def ocr_image(path: Path) -> str:
    if path.suffix.lower() != ".heic":
        return _tesseract(path)
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / "page.jpg"
        subprocess.run(
            [_need("sips"), "-s", "format", "jpeg", str(path), "--out", str(jpg)],
            capture_output=True, check=True, timeout=60,
        )
        return _tesseract(jpg)


def ocr_pdf(path: Path) -> str:
    """Rasterise each page at 300 dpi, OCR it. For scans with no text layer."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [_need("pdftoppm"), "-r", "300", "-png", str(path), str(Path(tmp) / "p")],
            capture_output=True, check=True, timeout=600,
        )
        pages = sorted(Path(tmp).glob("p*.png"))
        return "\n\n".join(_tesseract(p) for p in pages)
