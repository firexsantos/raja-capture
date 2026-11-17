"""Render the SVG logo to PNG (Linux/AppImage) and ICO (Windows) into packaging/build/."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "..", "raja_capture", "assets", "raja-capture.svg")
OUT = os.path.join(HERE, "build")


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(SVG).render(p)
    p.end()
    return img


def main():
    QGuiApplication(sys.argv[:1])
    os.makedirs(OUT, exist_ok=True)
    render(256).save(os.path.join(OUT, "raja-capture.png"))
    ok = render(256).save(os.path.join(OUT, "raja-capture.ico"), "ICO")
    print("icons written to", OUT, "(ico ok)" if ok else "(ico plugin missing, skipped)")


if __name__ == "__main__":
    main()
