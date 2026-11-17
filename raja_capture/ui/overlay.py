"""Fullscreen selection overlay drawn on top of a frozen desktop screenshot.

One overlay window is shown per monitor. Modes:

* ``region``  - drag a rectangle
* ``window``  - hover highlights windows (when the backend lists them); click to
                pick, or drag a region
* ``color``   - magnified pixel picker
* ``ruler``   - drag to measure distances (multiple measurements, Esc to exit)
"""

from __future__ import annotations

import math

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from ..capture.base import DesktopShot

SEL_COLOR = QColor(0, 160, 255)
DIM = QColor(0, 0, 0, 105)

HINTS = {
    "region": "Seret untuk memilih area   •   Esc / klik kanan: batal",
    "window": "Klik jendela untuk menangkap   •   seret untuk area   •   Esc: batal",
    "window_noenum": "Seret untuk memilih area, atau klik untuk seluruh layar ini   •   Esc: batal",
    "color": "Klik untuk mengambil warna   •   Esc / klik kanan: batal",
    "ruler": "Seret untuk mengukur (Shift = lurus)   •   Esc / klik kanan: selesai",
}


class OverlayController(QObject):
    regionSelected = Signal(QRect, QRect, object)  # image rect, logical rect, QScreen
    colorPicked = Signal(QColor)
    cancelled = Signal()

    def __init__(self, shot: DesktopShot, mode: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.shot = shot
        self.mode = mode
        if not hint:
            key = mode
            if mode == "window" and not shot.windows:
                key = "window_noenum"
            hint = HINTS.get(key, "")
        self.hint = hint
        self.overlays = [SelectionOverlay(self, s) for s in QGuiApplication.screens()]
        self._done = False

    def start(self):
        current = QGuiApplication.screenAt(QCursor.pos())
        for ov in self.overlays:
            ov.show_on_screen()
        for ov in self.overlays:
            if ov.screen_ is current:
                ov.raise_()
                ov.activateWindow()
                ov.setFocus()

    def _close(self):
        self._done = True
        overlays, self.overlays = self.overlays, []
        for ov in overlays:
            ov.hide()
            ov.close()
            ov.deleteLater()

    def finish_region(self, img_rect: QRect, logical_rect: QRect, screen):
        if self._done:
            return
        self._close()
        if img_rect.width() < 1 or img_rect.height() < 1:
            self.cancelled.emit()
            return
        self.regionSelected.emit(img_rect, logical_rect, screen)

    def finish_color(self, color: QColor):
        if self._done:
            return
        self._close()
        self.colorPicked.emit(color)

    def cancel(self):
        if self._done:
            return
        self._close()
        self.cancelled.emit()

    def mouse_entered(self, overlay):
        for ov in self.overlays:
            if ov is not overlay and ov.mouse is not None:
                ov.mouse = None
                ov.update()


class SelectionOverlay(QWidget):
    def __init__(self, ctrl: OverlayController, screen):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.ctrl = ctrl
        self.screen_ = screen
        self.geo = screen.geometry()
        shot = ctrl.shot
        self.img_rect = shot.logical_to_image(self.geo)
        self.sub: QImage = shot.image.copy(self.img_rect)
        self.sx = self.img_rect.width() / max(1, self.geo.width())
        self.sy = self.img_rect.height() / max(1, self.geo.height())
        self.pix = QPixmap.fromImage(self.sub)
        self.setWindowTitle("Raja Capture - pilih")
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.origin: QPoint | None = None
        self.cur: QPoint | None = None
        self.mouse: QPoint | None = None
        self.hover_rect: QRect | None = None  # image coords
        self.lines: list[tuple[QPointF, QPointF]] = []

    # ------------------------------------------------------------ geometry
    def show_on_screen(self):
        self.setScreen(self.screen_)
        self.setGeometry(self.geo)
        self.showFullScreen()

    def to_img(self, pt: QPointF) -> QPointF:
        return QPointF(self.img_rect.x() + pt.x() * self.sx, self.img_rect.y() + pt.y() * self.sy)

    def local_to_img_rect(self, r: QRect) -> QRect:
        x1 = round(r.left() * self.sx)
        y1 = round(r.top() * self.sy)
        x2 = round((r.left() + r.width()) * self.sx)
        y2 = round((r.top() + r.height()) * self.sy)
        return QRect(self.img_rect.x() + x1, self.img_rect.y() + y1, x2 - x1, y2 - y1).intersected(
            self.ctrl.shot.image.rect())

    def img_to_local_rect(self, r: QRect) -> QRectF:
        return QRectF(
            (r.x() - self.img_rect.x()) / self.sx,
            (r.y() - self.img_rect.y()) / self.sy,
            r.width() / self.sx,
            r.height() / self.sy,
        )

    def _sub_xy(self, pt: QPoint) -> tuple[int, int]:
        x = min(max(int(pt.x() * self.sx), 0), self.sub.width() - 1)
        y = min(max(int(pt.y() * self.sy), 0), self.sub.height() - 1)
        return x, y

    def color_at(self, pt: QPoint) -> QColor:
        return self.sub.pixelColor(*self._sub_xy(pt))

    def window_at(self, pt: QPoint) -> QRect | None:
        ip = self.to_img(QPointF(pt)).toPoint()
        for w in self.ctrl.shot.windows:
            if w.rect.contains(ip):
                return w.rect.intersected(self.ctrl.shot.image.rect())
        return None

    # ------------------------------------------------------------ painting
    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        mode = self.ctrl.mode
        if mode in ("region", "window"):
            self._paint_selection(p, mode)
        elif mode == "ruler":
            self._paint_ruler(p)
        if mode == "color":
            self._paint_magnifier(p, big=True)
        elif mode in ("region", "window") and self.mouse is not None:
            self._paint_magnifier(p)
        if self.ctrl.hint and (self.mouse is not None or len(self.ctrl.overlays) == 1):
            self._paint_hint(p)
        p.end()

    def _paint_selection(self, p: QPainter, mode: str):
        sel = None
        if self.origin is not None and self.cur is not None:
            sel = QRectF(QRect(self.origin, self.cur).normalized())
        elif mode == "window" and self.hover_rect is not None:
            sel = self.img_to_local_rect(self.hover_rect)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if sel is not None:
            path.addRect(sel)
        p.fillPath(path, DIM)
        if sel is not None:
            p.setPen(QPen(SEL_COLOR, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sel.adjusted(-1, -1, 1, 1))
            w, h = round(sel.width() * self.sx), round(sel.height() * self.sy)
            self._label(p, f"{w} × {h}", sel.topLeft() + QPointF(0, -6), above=True)
        elif self.mouse is not None:
            p.setPen(QPen(QColor(SEL_COLOR.red(), SEL_COLOR.green(), SEL_COLOR.blue(), 170), 1, Qt.DashLine))
            p.drawLine(0, self.mouse.y(), self.width(), self.mouse.y())
            p.drawLine(self.mouse.x(), 0, self.mouse.x(), self.height())

    def _paint_ruler(self, p: QPainter):
        p.setRenderHint(QPainter.Antialiasing)
        lines = list(self.lines)
        if self.origin is not None and self.cur is not None:
            lines.append((QPointF(self.origin), QPointF(self.cur)))
        for a, b in lines:
            p.setPen(QPen(QColor(0, 0, 0, 160), 4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)
            p.setPen(QPen(QColor(255, 214, 0), 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)
            for pt in (a, b):
                p.drawEllipse(pt, 3, 3)
            dx = (b.x() - a.x()) * self.sx
            dy = (b.y() - a.y()) * self.sy
            length = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(-dy, dx))
            text = f"{length:.0f} px   (Δx {abs(dx):.0f}, Δy {abs(dy):.0f}, {angle:.1f}°)"
            mid = (a + b) / 2
            self._label(p, text, mid + QPointF(8, -8), above=True)
        if self.mouse is not None and self.origin is None:
            p.setPen(QPen(QColor(255, 214, 0, 160), 1, Qt.DashLine))
            p.drawLine(0, self.mouse.y(), self.width(), self.mouse.y())
            p.drawLine(self.mouse.x(), 0, self.mouse.x(), self.height())
            ip = self.to_img(QPointF(self.mouse))
            self._label(p, f"{ip.x():.0f}, {ip.y():.0f}", QPointF(self.mouse) + QPointF(12, 22))

    def _label(self, p: QPainter, text: str, pos: QPointF, above=False):
        f = QFont()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 12, fm.height() + 6
        x = min(max(pos.x(), 2), self.width() - w - 2)
        y = pos.y() - h if above else pos.y()
        if y < 2:
            y = pos.y() + 8 if above else 2
        y = min(y, self.height() - h - 2)
        box = QRectF(x, y, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 20, 210))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(Qt.white)
        p.drawText(box, Qt.AlignCenter, text)

    def _paint_hint(self, p: QPainter):
        f = QFont()
        f.setPixelSize(14)
        p.setFont(f)
        fm = p.fontMetrics()
        text = self.ctrl.hint
        w, h = fm.horizontalAdvance(text) + 28, fm.height() + 14
        box = QRectF((self.width() - w) / 2, 16, w, h)
        if self.mouse is not None and box.adjusted(-20, -20, 20, 20).contains(QPointF(self.mouse)):
            box.moveBottom(self.height() - 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 20, 200))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(Qt.white)
        p.drawText(box, Qt.AlignCenter, text)

    def _paint_magnifier(self, p: QPainter, big=False):
        if self.mouse is None:
            return
        n = 21 if big else 15
        cell = 8
        size = n * cell
        sx, sy = self._sub_xy(self.mouse)
        src = QRect(sx - n // 2, sy - n // 2, n, n)
        piece = QImage(n, n, QImage.Format_RGB32)
        piece.fill(QColor(0, 0, 0))
        inter = src.intersected(self.sub.rect())
        qp = QPainter(piece)
        qp.drawImage(inter.topLeft() - src.topLeft(), self.sub, inter)
        qp.end()

        info_h = 40
        info_w = max(size, 210)
        x = self.mouse.x() + 24
        y = self.mouse.y() + 24
        if x + info_w > self.width():
            x = self.mouse.x() - 24 - info_w
        if y + size + info_h > self.height():
            y = self.mouse.y() - 24 - size - info_h
        target = QRect(x, y, size, size)
        p.save()
        p.setBrush(Qt.NoBrush)  # earlier labels leave a dark brush set; rects must not be filled
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(target, piece)
        if big:
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
            for i in range(1, n):
                p.drawLine(x + i * cell, y, x + i * cell, y + size)
                p.drawLine(x, y + i * cell, x + size, y + i * cell)
        c = QRect(x + (n // 2) * cell, y + (n // 2) * cell, cell, cell)
        p.setPen(QPen(Qt.white, 1))
        p.drawRect(c)
        p.setPen(QPen(Qt.black, 1))
        p.drawRect(c.adjusted(-1, -1, 1, 1))
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawRect(target)
        color = self.sub.pixelColor(sx, sy)
        info = QRect(x, y + size, info_w, info_h)
        p.fillRect(info, QColor(20, 20, 20, 225))
        p.fillRect(QRect(info.x() + 6, info.y() + 8, 24, 24), color)
        p.setPen(Qt.white)
        f = QFont()
        f.setPixelSize(12)
        p.setFont(f)
        gx, gy = self.img_rect.x() + sx, self.img_rect.y() + sy
        p.drawText(info.adjusted(36, 2, -4, -2), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{color.name().upper()}  rgb({color.red()},{color.green()},{color.blue()})\n"
                   f"x {gx}, y {gy}")
        p.restore()

    # ------------------------------------------------------------ input
    def _pos(self, event) -> QPoint:
        return event.position().toPoint()

    def _constrain(self, origin: QPoint, pt: QPoint, modifiers) -> QPoint:
        if self.ctrl.mode == "ruler" and modifiers & Qt.ShiftModifier:
            if abs(pt.x() - origin.x()) >= abs(pt.y() - origin.y()):
                return QPoint(pt.x(), origin.y())
            return QPoint(origin.x(), pt.y())
        return pt

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.ctrl.cancel()
            return
        if e.button() != Qt.LeftButton:
            return
        pos = self._pos(e)
        if self.ctrl.mode == "color":
            self.ctrl.finish_color(self.color_at(pos))
            return
        self.origin = pos
        self.cur = pos
        self.update()

    def mouseMoveEvent(self, e):
        pos = self._pos(e)
        if self.mouse is None:
            self.ctrl.mouse_entered(self)
        self.mouse = pos
        if self.origin is not None:
            self.cur = self._constrain(self.origin, pos, e.modifiers())
        elif self.ctrl.mode == "window":
            self.hover_rect = self.window_at(pos)
        self.update()

    def leaveEvent(self, _e):
        self.mouse = None
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.origin is None:
            return
        end = self._constrain(self.origin, self._pos(e), e.modifiers())
        origin, self.origin, self.cur = self.origin, None, None
        mode = self.ctrl.mode
        if mode == "ruler":
            if (end - origin).manhattanLength() > 2:
                self.lines.append((QPointF(origin), QPointF(end)))
            self.update()
            return
        r = QRect(origin, end).normalized()
        if r.width() >= 3 and r.height() >= 3:
            self.ctrl.finish_region(self.local_to_img_rect(r), r.translated(self.geo.topLeft()), self.screen_)
        elif mode == "window":
            if self.hover_rect is not None:
                self.ctrl.finish_region(self.hover_rect, self.ctrl.shot.image_to_logical(self.hover_rect),
                                        self.screen_)
            elif not self.ctrl.shot.windows:
                self.ctrl.finish_region(self.img_rect, QRect(self.geo), self.screen_)
            else:
                self.update()
        else:
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.ctrl.cancel()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.ctrl.mode in ("region", "window"):
            # Enter = capture this whole monitor
            self.ctrl.finish_region(self.img_rect, QRect(self.geo), self.screen_)
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if not self.ctrl._done:
            self.ctrl.cancel()
        super().closeEvent(e)

    def sizeHint(self):
        return QSize(self.geo.width(), self.geo.height())
