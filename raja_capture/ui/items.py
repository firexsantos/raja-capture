"""Annotation graphics items for the editor."""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

FLAGS = QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
HIGHLIGHT_YELLOW = QColor("#ffeb3b")


def make_pen(color, width) -> QPen:
    pen = QPen(QColor(color), float(width))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def selection_pen() -> QPen:
    pen = QPen(QColor(0, 140, 255), 1, Qt.DashLine)
    pen.setCosmetic(True)
    return pen


class Annotation:
    """Mixin: style storage shared by all annotation items."""

    kind = "base"

    def init_style(self, **style):
        self._style = {"color": QColor("#e53935"), "width": 3, "fill": False, "font_size": 24}
        self._style.update({k: v for k, v in style.items() if v is not None})
        self._style["color"] = QColor(self._style["color"])
        self.refresh_style()

    def get_style(self) -> dict:
        s = dict(self._style)
        s["color"] = QColor(s["color"])
        return s

    def apply_style(self, **kw):
        for k, v in kw.items():
            if v is not None and k in self._style:
                self._style[k] = QColor(v) if k == "color" else v
        self.refresh_style()

    def refresh_style(self):
        pass


RECT_HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")
HANDLE_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
    "bl": Qt.SizeBDiagCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor, "p1": Qt.SizeAllCursor, "p2": Qt.SizeAllCursor,
}


class RectGeometry:
    """Mixin for rect-based items: 8 resize handles."""

    resizable = True

    def control_points(self) -> dict:
        r = self.rect()
        c = r.center()
        pts = {
            "tl": r.topLeft(), "t": QPointF(c.x(), r.top()), "tr": r.topRight(),
            "r": QPointF(r.right(), c.y()), "br": r.bottomRight(), "b": QPointF(c.x(), r.bottom()),
            "bl": r.bottomLeft(), "l": QPointF(r.left(), c.y()),
        }
        return {k: self.mapToScene(v) for k, v in pts.items()}

    def get_geometry(self):
        return QRectF(self.rect())

    def set_geometry(self, g):
        self.setRect(QRectF(g))

    def move_control(self, key: str, scene_pt: QPointF, start, shift: bool = False):
        p = self.mapFromScene(scene_pt)
        r = QRectF(start)
        if key in ("tl", "l", "bl"):
            r.setLeft(p.x())
        if key in ("tr", "r", "br"):
            r.setRight(p.x())
        if key in ("tl", "t", "tr"):
            r.setTop(p.y())
        if key in ("bl", "b", "br"):
            r.setBottom(p.y())
        if shift and key in ("tl", "tr", "bl", "br"):
            s = max(abs(r.width()), abs(r.height()))
            if key in ("tl", "bl"):
                r.setLeft(r.right() - s if r.width() >= 0 else r.right() + s)
            else:
                r.setRight(r.left() + s if r.width() >= 0 else r.left() - s)
            if key in ("tl", "tr"):
                r.setTop(r.bottom() - s if r.height() >= 0 else r.bottom() + s)
            else:
                r.setBottom(r.top() + s if r.height() >= 0 else r.top() - s)
        self.setRect(r.normalized())


class LineGeometry:
    """Mixin for line-based items: 2 endpoint handles."""

    resizable = True

    def control_points(self) -> dict:
        line = self.line()
        return {"p1": self.mapToScene(line.p1()), "p2": self.mapToScene(line.p2())}

    def get_geometry(self):
        return QLineF(self.line())

    def set_geometry(self, g):
        self.setLine(QLineF(g))

    def move_control(self, key: str, scene_pt: QPointF, start, shift: bool = False):
        p = self.mapFromScene(scene_pt)
        line = QLineF(start)
        anchor = line.p2() if key == "p1" else line.p1()
        if shift:
            dx, dy = p.x() - anchor.x(), p.y() - anchor.y()
            length = math.hypot(dx, dy)
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            p = QPointF(anchor.x() + length * math.cos(ang), anchor.y() + length * math.sin(ang))
        if key == "p1":
            line.setP1(p)
        else:
            line.setP2(p)
        self.setLine(line)


class RectItem(RectGeometry, QGraphicsRectItem, Annotation):
    kind = "rect"

    def __init__(self, rect: QRectF, **style):
        super().__init__(rect)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def refresh_style(self):
        s = self._style
        self.setPen(make_pen(s["color"], s["width"]))
        self.setBrush(QBrush(s["color"]) if s["fill"] else Qt.NoBrush)


class EllipseItem(RectGeometry, QGraphicsEllipseItem, Annotation):
    kind = "ellipse"

    def __init__(self, rect: QRectF, **style):
        super().__init__(rect)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def refresh_style(self):
        s = self._style
        self.setPen(make_pen(s["color"], s["width"]))
        self.setBrush(QBrush(s["color"]) if s["fill"] else Qt.NoBrush)


class LineItem(LineGeometry, QGraphicsLineItem, Annotation):
    kind = "line"

    def __init__(self, line: QLineF, **style):
        super().__init__(line)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def refresh_style(self):
        self.setPen(make_pen(self._style["color"], self._style["width"]))


class PenItem(QGraphicsPathItem, Annotation):
    kind = "pen"

    def __init__(self, start: QPointF, **style):
        path = QPainterPath(start)
        path.lineTo(start + QPointF(0.01, 0.01))
        super().__init__(path)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def refresh_style(self):
        self.setPen(make_pen(self._style["color"], self._style["width"]))
        self.setBrush(Qt.NoBrush)


class ArrowItem(LineGeometry, QGraphicsItem, Annotation):
    kind = "arrow"

    def __init__(self, line: QLineF, **style):
        super().__init__()
        self._line = QLineF(line)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def line(self) -> QLineF:
        return QLineF(self._line)

    def setLine(self, line: QLineF):
        self.prepareGeometryChange()
        self._line = QLineF(line)
        self.update()

    def refresh_style(self):
        self.prepareGeometryChange()
        self.update()

    def _head_len(self) -> float:
        return max(12.0, float(self._style["width"]) * 4.5)

    def _head(self):
        length = self._line.length()
        if length < 0.5:
            return None
        L = min(self._head_len(), length)
        W = L * 0.42
        ux, uy = self._line.dx() / length, self._line.dy() / length
        tip = self._line.p2()
        base = QPointF(tip.x() - ux * L, tip.y() - uy * L)
        nx, ny = -uy, ux
        poly = QPolygonF([
            tip,
            QPointF(base.x() + nx * W, base.y() + ny * W),
            QPointF(base.x() - nx * W, base.y() - ny * W),
        ])
        return poly, base

    def boundingRect(self) -> QRectF:
        m = self._head_len() + float(self._style["width"]) + 4
        return QRectF(self._line.p1(), self._line.p2()).normalized().adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath(self._line.p1())
        path.lineTo(self._line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(10.0, float(self._style["width"]) + 8))
        shape = stroker.createStroke(path)
        head = self._head()
        if head:
            shape.addPolygon(head[0])
        return shape

    def paint(self, p: QPainter, _option, _widget=None):
        color = self._style["color"]
        p.setRenderHint(QPainter.Antialiasing)
        head = self._head()
        if head:
            poly, base = head
            p.setPen(make_pen(color, self._style["width"]))
            if self._line.length() > self._head_len():
                p.drawLine(QLineF(self._line.p1(), base))
            p.setPen(QPen(color, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(color)
            p.drawPolygon(poly)
        if self.isSelected():
            p.setPen(selection_pen())
            p.setBrush(Qt.NoBrush)
            for pt in (self._line.p1(), self._line.p2()):
                p.drawEllipse(pt, 5, 5)


class HighlightItem(RectGeometry, QGraphicsRectItem, Annotation):
    kind = "highlight"

    def __init__(self, rect: QRectF, **style):
        super().__init__(rect)
        self.setFlags(FLAGS)
        style.setdefault("color", HIGHLIGHT_YELLOW)
        self.init_style(**style)

    def refresh_style(self):
        self.setPen(Qt.NoPen)
        self.update()

    def paint(self, p: QPainter, _option, _widget=None):
        p.save()
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.fillRect(self.rect(), self._style["color"])
        p.restore()
        if self.isSelected():
            p.setPen(selection_pen())
            p.drawRect(self.rect())


class PixelateItem(RectGeometry, QGraphicsRectItem, Annotation):
    """Pixelates the base screenshot underneath it (for hiding sensitive info)."""

    kind = "pixelate"

    def __init__(self, rect: QRectF, base_item, **style):
        super().__init__(rect)
        self.base_item = base_item
        self.setFlags(FLAGS)
        self.init_style(**style)

    def refresh_style(self):
        self.setPen(Qt.NoPen)
        self.update()

    def paint(self, p: QPainter, _option, _widget=None):
        pm = self.base_item.pixmap()
        scene_r = self.mapRectToScene(self.rect())
        src = scene_r.intersected(QRectF(pm.rect())).toAlignedRect()
        if src.width() > 0 and src.height() > 0:
            block = max(4, int(float(self._style["width"]) * 3))
            img = pm.copy(src).toImage()
            small = img.scaled(max(1, img.width() // block), max(1, img.height() // block),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            big = small.scaled(img.width(), img.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.drawImage(self.mapRectFromScene(QRectF(src)), big)
        if self.isSelected():
            p.setPen(selection_pen())
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect())


class StepItem(QGraphicsItem, Annotation):
    """Numbered circle marker (1, 2, 3, ...) for step-by-step tutorials."""

    kind = "step"

    def __init__(self, center: QPointF, number: int, **style):
        super().__init__()
        self.number = number
        self.setPos(center)
        self.setFlags(FLAGS)
        self.init_style(**style)

    def _d(self) -> float:
        return 22 + float(self._style["width"]) * 3

    def refresh_style(self):
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        d = self._d()
        return QRectF(-d / 2 - 2, -d / 2 - 2, d + 4, d + 4)

    def paint(self, p: QPainter, _option, _widget=None):
        d = self._d()
        color = self._style["color"]
        r = QRectF(-d / 2, -d / 2, d, d)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(Qt.white, 2))
        p.setBrush(color)
        p.drawEllipse(r)
        lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        p.setPen(Qt.black if lum > 170 else Qt.white)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(8, int(d * 0.5)))
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, str(self.number))
        if self.isSelected():
            p.setPen(selection_pen())
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.boundingRect())


class TextItem(QGraphicsTextItem, Annotation):
    kind = "text"

    def __init__(self, pos: QPointF, **style):
        super().__init__()
        self.setPos(pos)
        self.setFlags(FLAGS | QGraphicsItem.ItemIsFocusable)
        self.on_edit_done = None
        self.init_style(**style)

    def refresh_style(self):
        s = self._style
        self.setDefaultTextColor(s["color"])
        f = QFont(self.font())
        f.setPixelSize(max(6, int(s["font_size"])))
        f.setBold(True)
        self.setFont(f)
        self.update()

    def is_editing(self) -> bool:
        return bool(self.textInteractionFlags() & Qt.TextEditorInteraction)

    def start_edit(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        if self.on_edit_done:
            self.on_edit_done(self)

    def mouseDoubleClickEvent(self, event):
        self.start_edit()
        super().mouseDoubleClickEvent(event)

    def paint(self, p: QPainter, option, widget=None):
        if self._style["fill"]:
            p.fillRect(self.boundingRect(), QColor(255, 255, 255, 230))
        super().paint(p, option, widget)


def is_annotation(item) -> bool:
    return isinstance(item, Annotation)


class HandleItem(QGraphicsRectItem):
    """A resize handle; constant on-screen size regardless of zoom."""

    SIZE = 9

    def __init__(self, target, key: str, on_done):
        s = self.SIZE
        super().__init__(-s / 2, -s / 2, s, s)
        self.target, self.key, self.on_done = target, key, on_done
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(2_000_000)
        self.setBrush(QColor(255, 255, 255))
        pen = QPen(QColor(0, 140, 255), 1.5)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setCursor(HANDLE_CURSORS.get(key, Qt.SizeAllCursor))
        self._start = None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            e.ignore()
            return
        self._start = self.target.get_geometry()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._start is None:
            return
        self.target.move_control(self.key, e.scenePos(), self._start,
                                 bool(e.modifiers() & Qt.ShiftModifier))
        if self.scene() is not None:
            for h in [i for i in self.scene().items() if isinstance(i, HandleItem)]:
                h.setPos(h.target.control_points()[h.key])

    def mouseReleaseEvent(self, e):
        if self._start is not None:
            start, self._start = self._start, None
            self.on_done(self.target, start, self.target.get_geometry())
        e.accept()
