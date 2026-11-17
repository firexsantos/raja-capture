"""Programmatically drawn toolbar icons (theme-aware, no image files needed)."""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)

ACCENT = QColor("#1e88e5")
RED = QColor("#e53935")
_cache: dict[tuple, QIcon] = {}

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


def app_icon() -> QIcon:
    path = os.path.join(ASSET_DIR, "raja-capture.svg")
    if os.path.exists(path):
        return QIcon(path)
    return icon("region")


def _fg() -> QColor:
    app = QGuiApplication.instance()
    if app is None:
        return QColor("#333")
    return app.palette().color(QPalette.WindowText)


def _arrow_head(p: QPainter, tip: QPointF, frm: QPointF, size=5.0):
    import math

    ang = math.atan2(tip.y() - frm.y(), tip.x() - frm.x())
    a1, a2 = ang + math.radians(150), ang - math.radians(150)
    poly = QPolygonF([
        tip,
        QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
        QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
    ])
    p.save()
    p.setBrush(p.pen().color())
    p.setPen(Qt.NoPen)
    p.drawPolygon(poly)
    p.restore()


def _draw(name: str, p: QPainter, fg: QColor):
    pen = QPen(fg, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if name == "full":
        p.drawRoundedRect(QRectF(3, 4, 18, 12), 1.5, 1.5)
        p.fillRect(QRectF(5, 6, 14, 8), QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 110))
        p.drawLine(QPointF(12, 16), QPointF(12, 19.5))
        p.drawLine(QPointF(8, 20), QPointF(16, 20))
    elif name == "window":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 1.5, 1.5)
        p.fillRect(QRectF(3.8, 5.8, 16.4, 3), ACCENT)
        p.drawLine(QPointF(3, 9), QPointF(21, 9))
    elif name == "region":
        dash = QPen(fg, 1.6, Qt.DashLine)
        p.setPen(dash)
        p.drawRect(QRectF(5, 5, 14, 14))
        p.setPen(QPen(ACCENT, 2.4, Qt.SolidLine, Qt.SquareCap))
        for x, y, dx, dy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 5 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 5 * dy))
    elif name == "scroll":
        p.drawRoundedRect(QRectF(4, 2.5, 13, 15), 1.5, 1.5)
        p.setPen(QPen(ACCENT, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(19.5, 8), QPointF(19.5, 20))
        _arrow_head(p, QPointF(19.5, 22), QPointF(19.5, 10), 5)
        p.setPen(QPen(fg, 1.2))
        for y in (6, 9, 12):
            p.drawLine(QPointF(7, y), QPointF(14, y))
    elif name == "record":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.setBrush(RED)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(7.5, 7.5, 9, 9))
    elif name == "stop":
        p.setBrush(RED)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
    elif name == "color":
        p.setPen(QPen(fg, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(5, 19), QPointF(14, 10))
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawEllipse(QRectF(13, 4, 7, 7))
        p.setBrush(RED)
        p.drawEllipse(QRectF(3, 17.5, 4, 4))
    elif name == "ruler":
        p.save()
        p.translate(12, 12)
        p.rotate(-35)
        p.drawRect(QRectF(-10, -3.5, 20, 7))
        for i, x in enumerate(range(-7, 9, 3)):
            p.drawLine(QPointF(x, -3.5), QPointF(x, -3.5 + (3.5 if i % 2 == 0 else 2)))
        p.restore()
    elif name == "ocr":
        p.setPen(QPen(ACCENT, 2, Qt.SolidLine, Qt.SquareCap))
        for x, y, dx, dy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 4 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 4 * dy))
        p.setPen(QPen(fg, 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(8, 8), QPointF(16, 8))
        p.drawLine(QPointF(12, 8), QPointF(12, 17))
    elif name == "open":
        path = QPainterPath()
        path.moveTo(3, 6)
        path.lineTo(9, 6)
        path.lineTo(11, 8)
        path.lineTo(21, 8)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
        p.fillRect(QRectF(4, 11, 16, 7), QColor(255, 193, 7, 160))
    elif name == "settings":
        import math

        p.save()
        p.translate(12, 12)
        p.setPen(QPen(fg, 3, Qt.SolidLine, Qt.RoundCap))
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(6 * math.cos(a), 6 * math.sin(a)), QPointF(8.5 * math.cos(a), 8.5 * math.sin(a)))
        p.setPen(QPen(fg, 1.8))
        p.drawEllipse(QPointF(0, 0), 5.5, 5.5)
        p.drawEllipse(QPointF(0, 0), 2.2, 2.2)
        p.restore()
    elif name == "select":
        poly = QPolygonF([QPointF(6, 3), QPointF(6, 19), QPointF(10, 15), QPointF(13, 21),
                          QPointF(15.5, 20), QPointF(12.5, 14), QPointF(18, 14)])
        p.setBrush(QColor(fg.red(), fg.green(), fg.blue(), 60))
        p.drawPolygon(poly)
    elif name == "arrow":
        p.setPen(QPen(RED, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(4, 20), QPointF(16, 8))
        _arrow_head(p, QPointF(20, 4), QPointF(4, 20), 8)
    elif name == "line":
        p.setPen(QPen(RED, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(4, 20), QPointF(20, 4))
    elif name == "rect":
        p.setPen(QPen(RED, 2.2))
        p.drawRect(QRectF(4, 6, 16, 12))
    elif name == "ellipse":
        p.setPen(QPen(RED, 2.2))
        p.drawEllipse(QRectF(3, 6, 18, 12))
    elif name == "highlight":
        p.fillRect(QRectF(3, 9, 18, 7), QColor(255, 235, 59, 200))
        p.setPen(QPen(fg, 1.2))
        p.drawLine(QPointF(5, 12.5), QPointF(19, 12.5))
    elif name == "pen":
        path = QPainterPath(QPointF(3, 17))
        path.cubicTo(QPointF(7, 5), QPointF(11, 21), QPointF(14, 11))
        path.cubicTo(QPointF(16, 6), QPointF(19, 9), QPointF(21, 6))
        p.setPen(QPen(RED, 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
    elif name == "text":
        f = QFont()
        f.setPixelSize(17)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(2, 1, 20, 22), Qt.AlignCenter, "A")
    elif name == "pixelate":
        shades = [60, 140, 90, 170, 110, 200, 80, 150, 120]
        for i, s in enumerate(shades):
            r, c = divmod(i, 3)
            p.fillRect(QRectF(4 + c * 5.5, 4 + r * 5.5, 5.5, 5.5), QColor(s, s, s))
    elif name == "step":
        p.setBrush(RED)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(3, 3, 18, 18))
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(Qt.white)
        p.drawText(QRectF(3, 3, 18, 18), Qt.AlignCenter, "1")
    elif name == "crop":
        p.setPen(QPen(fg, 2.2, Qt.SolidLine, Qt.SquareCap))
        p.drawPolyline(QPolygonF([QPointF(7, 2), QPointF(7, 17), QPointF(22, 17)]))
        p.drawPolyline(QPolygonF([QPointF(2, 7), QPointF(17, 7), QPointF(17, 22)]))
    elif name == "save":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
        p.fillRect(QRectF(8, 4.8, 8, 5), ACCENT)
        p.drawRect(QRectF(7, 13, 10, 6.2))
    elif name == "save_as":
        _draw("save", p, fg)
        p.setPen(QPen(RED, 2))
        p.drawLine(QPointF(17, 20), QPointF(22, 15))
    elif name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 12, 13), 1.5, 1.5)
        p.drawPolyline(QPolygonF([QPointF(5, 16), QPointF(4, 16), QPointF(4, 3), QPointF(15, 3), QPointF(15, 5)]))
    elif name == "print":
        p.drawRect(QRectF(7, 3, 10, 6))
        p.drawRoundedRect(QRectF(3, 9, 18, 8), 1.5, 1.5)
        p.drawRect(QRectF(7, 14, 10, 7))
    elif name in ("undo", "redo"):
        p.save()
        if name == "redo":
            p.translate(24, 0)
            p.scale(-1, 1)
        path = QPainterPath(QPointF(6, 10))
        path.cubicTo(QPointF(12, 4), QPointF(22, 8), QPointF(18, 19))
        p.drawPath(path)
        _arrow_head(p, QPointF(4, 11.5), QPointF(12, 5), 7)
        p.restore()
    elif name in ("zoom_in", "zoom_out", "zoom_fit", "zoom_100"):
        p.drawEllipse(QRectF(3, 3, 13, 13))
        p.setPen(QPen(fg, 2.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(14.5, 14.5), QPointF(20.5, 20.5))
        p.setPen(QPen(fg, 1.6))
        if name in ("zoom_in", "zoom_out"):
            p.drawLine(QPointF(6.5, 9.5), QPointF(12.5, 9.5))
        if name == "zoom_in":
            p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 12.5))
        if name == "zoom_fit":
            p.drawRect(QRectF(6.5, 7, 6, 5))
        if name == "zoom_100":
            f = QFont()
            f.setPixelSize(7)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(3, 3, 13, 13), Qt.AlignCenter, "1:1")
    elif name in ("rotate_left", "rotate_right"):
        p.save()
        if name == "rotate_right":
            p.translate(24, 0)
            p.scale(-1, 1)
        p.drawRect(QRectF(9, 9, 11, 11))
        path = QPainterPath(QPointF(13, 4))
        path.cubicTo(QPointF(7, 3), QPointF(4, 6), QPointF(4, 12))
        p.drawPath(path)
        _arrow_head(p, QPointF(4, 14), QPointF(4, 6), 6)
        p.restore()
    elif name in ("flip_h", "flip_v"):
        p.save()
        if name == "flip_v":
            p.translate(12, 12)
            p.rotate(90)
            p.translate(-12, -12)
        p.setPen(QPen(fg, 1.2, Qt.DashLine))
        p.drawLine(QPointF(12, 2), QPointF(12, 22))
        p.setPen(pen)
        p.setBrush(QColor(fg.red(), fg.green(), fg.blue(), 90))
        p.drawPolygon(QPolygonF([QPointF(10, 5), QPointF(10, 19), QPointF(3, 19)]))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([QPointF(14, 5), QPointF(14, 19), QPointF(21, 19)]))
        p.restore()
    elif name == "resize":
        p.drawRect(QRectF(3, 9, 12, 12))
        p.setPen(QPen(ACCENT, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(12, 12), QPointF(19, 5))
        _arrow_head(p, QPointF(21, 3), QPointF(12, 12), 6)
    elif name == "delete":
        p.setPen(QPen(RED, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name in ("send", "upload"):
        if name == "upload":
            p.drawPolyline(QPolygonF([QPointF(4, 15), QPointF(4, 20), QPointF(20, 20), QPointF(20, 15)]))
            p.setPen(QPen(ACCENT, 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(12, 16), QPointF(12, 6))
            _arrow_head(p, QPointF(12, 3), QPointF(12, 16), 7)
        else:
            poly = QPolygonF([QPointF(3, 11), QPointF(21, 3), QPointF(14, 21), QPointF(11, 13)])
            p.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 90))
            p.drawPolygon(poly)
            p.drawLine(QPointF(11, 13), QPointF(21, 3))
    elif name == "fill":
        p.setBrush(QColor(fg.red(), fg.green(), fg.blue(), 140))
        p.drawRoundedRect(QRectF(4, 6, 16, 12), 2, 2)
    else:
        p.drawRect(QRectF(4, 4, 16, 16))


def icon(name: str) -> QIcon:
    fg = _fg()
    key = (name, fg.rgba())
    if key in _cache:
        return _cache[key]
    ic = QIcon()
    for size in (24, 48):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(size / 24.0, size / 24.0)
        _draw(name, p, fg)
        p.end()
        ic.addPixmap(pm)
    _cache[key] = ic
    return ic


def color_swatch_icon(color: QColor, size: int = 20) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(0, 0, 0, 120), 1))
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(1.5, 1.5, size - 3, size - 3), 3, 3)
    p.end()
    return QIcon(pm)
