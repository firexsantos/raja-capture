"""Saving images in the supported formats (PNG/JPG/BMP/WEBP/PDF)."""

from __future__ import annotations

import os

from PySide6.QtCore import QMarginsF, QRect, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

SAVE_FILTER = (
    "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;WEBP (*.webp);;PDF (*.pdf)"
)
OPEN_FILTER = "Gambar (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff);;Semua file (*)"


def _flatten(img: QImage) -> QImage:
    out = QImage(img.size(), QImage.Format_RGB32)
    out.fill(QColor(255, 255, 255))
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def save_image(img: QImage, path: str, jpeg_quality: int = 92) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if ext == "pdf":
        writer = QPdfWriter(path)
        writer.setResolution(96)
        writer.setPageSize(QPageSize(QSizeF(img.width(), img.height()), QPageSize.Point))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Point)
        writer.setCreator("Raja Capture")
        p = QPainter(writer)
        target = QRect(0, 0, writer.width(), writer.height())
        scaled = img.size().scaled(target.size(), Qt.KeepAspectRatio)
        p.drawImage(QRect(target.topLeft(), scaled), img)
        p.end()
        return os.path.exists(path)
    if ext in ("jpg", "jpeg"):
        return _flatten(img).save(path, "JPG", jpeg_quality)
    if ext == "bmp":
        return _flatten(img).save(path, "BMP")
    if ext == "webp":
        return img.save(path, "WEBP", jpeg_quality)
    return img.save(path, "PNG")
