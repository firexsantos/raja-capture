"""OCR through the Tesseract command-line tool."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .util import IS_WINDOWS


class OcrError(Exception):
    pass


def find_tesseract(configured: str = "") -> str | None:
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    if IS_WINDOWS:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            path = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
            if os.path.exists(path):
                return path
    return None


def available_languages(exe: str) -> list[str]:
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15,
                             **_no_window()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.splitlines()[1:] if line.strip() and line.strip() != "osd"]


def _no_window() -> dict:
    if IS_WINDOWS:
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def run_ocr(img: QImage, lang: str = "eng", exe: str | None = None) -> str:
    """Blocking: run tesseract on ``img`` and return the recognised text."""
    exe = exe or find_tesseract()
    if not exe:
        raise OcrError(
            "Tesseract tidak ditemukan. Pasang 'tesseract-ocr' (Linux) atau Tesseract "
            "(Windows) lalu atur lokasinya di Pengaturan."
        )
    # Small screenshots OCR much better when upscaled.
    if img.height() < 800:
        factor = 2 if img.height() > 200 else 3
        img = img.scaled(img.width() * factor, img.height() * factor, Qt.KeepAspectRatio,
                         Qt.SmoothTransformation)
    with tempfile.TemporaryDirectory(prefix="raja-ocr-") as tmp:
        path = os.path.join(tmp, "ocr.png")
        img.save(path, "PNG")
        try:
            res = subprocess.run([exe, path, "stdout", "-l", lang or "eng", "--psm", "3"],
                                 capture_output=True, text=True, timeout=180, **_no_window())
        except subprocess.TimeoutExpired as exc:
            raise OcrError("OCR terlalu lama (timeout)") from exc
        except OSError as exc:
            raise OcrError(f"Gagal menjalankan tesseract: {exc}") from exc
    if res.returncode != 0:
        raise OcrError(res.stderr.strip() or "tesseract gagal")
    return res.stdout.strip()
