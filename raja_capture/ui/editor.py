"""Image editor window: annotate, crop, resize, save, copy, print, OCR."""

from __future__ import annotations

import os

from PySide6.QtCore import QLineF, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSpinBox,
    QToolButton,
    QWidget,
)

from ..config import next_filename
from ..imageio import OPEN_FILTER, SAVE_FILTER, save_image
from ..util import run_async
from . import icons
from .dialogs import ResizeDialog, TextResultDialog
from .items import (
    HIGHLIGHT_YELLOW,
    Annotation,
    ArrowItem,
    EllipseItem,
    HandleItem,
    HighlightItem,
    LineItem,
    PenItem,
    PixelateItem,
    RectItem,
    StepItem,
    TextItem,
)

TOOLS = [
    ("select", "Pilih / pindahkan", "V"),
    ("arrow", "Panah", "A"),
    ("line", "Garis", "L"),
    ("rect", "Kotak", "R"),
    ("ellipse", "Elips", "E"),
    ("highlight", "Stabilo (highlight)", "H"),
    ("pen", "Pena bebas", "P"),
    ("text", "Teks", "T"),
    ("step", "Nomor langkah", "N"),
    ("pixelate", "Sensor / pixelate", "B"),
    ("crop", "Potong (crop)", "C"),
]

QUICK_COLORS = ["#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa",
                "#000000", "#ffffff", "#757575"]


class FuncCommand(QUndoCommand):
    def __init__(self, text, redo, undo):
        super().__init__(text)
        self._redo, self._undo = redo, undo

    def redo(self):
        self._redo()

    def undo(self):
        self._undo()


def _snap45(start: QPointF, p: QPointF) -> QPointF:
    import math

    dx, dy = p.x() - start.x(), p.y() - start.y()
    length = math.hypot(dx, dy)
    ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    return QPointF(start.x() + length * math.cos(ang), start.y() + length * math.sin(ang))


def _square(start: QPointF, p: QPointF) -> QPointF:
    dx, dy = p.x() - start.x(), p.y() - start.y()
    s = max(abs(dx), abs(dy))
    return QPointF(start.x() + (s if dx >= 0 else -s), start.y() + (s if dy >= 0 else -s))


class CanvasView(QGraphicsView):
    def __init__(self, editor: "EditorWindow"):
        super().__init__(editor.scene)
        self.editor = editor
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor(58, 58, 62))
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._drawing = None
        self._start: QPointF | None = None
        self._moves = None
        self._pan_pos = None

    # zoom ---------------------------------------------------------------
    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, z: float):
        z = max(0.05, min(32.0, z))
        self.setTransform(QTransform.fromScale(z, z))
        self.setRenderHint(QPainter.SmoothPixmapTransform, z < 1.0)
        self.editor.on_zoom_changed(z)

    def zoom_by(self, factor: float):
        self.set_zoom(self.zoom() * factor)

    def fit(self):
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self.set_zoom(min(self.zoom(), 32.0))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.2 if e.angleDelta().y() > 0 else 1 / 1.2)
            e.accept()
        else:
            super().wheelEvent(e)

    # mouse --------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_pos = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        tool = self.editor.tool
        if tool == "select" or e.button() != Qt.LeftButton:
            super().mousePressEvent(e)
            if tool == "select":
                self._moves = {it: it.pos() for it in self.scene().selectedItems()}
            return
        p = self.mapToScene(e.position().toPoint())
        self._start = p
        if tool == "text":
            hit = self.itemAt(e.position().toPoint())
            if isinstance(hit, TextItem):
                super().mousePressEvent(e)
                hit.start_edit()
                return
            focus = self.scene().focusItem()
            if isinstance(focus, TextItem) and focus.is_editing():
                self.scene().clearFocus()  # finish current text first
                return
            self.editor.create_text(p)
            return
        if tool == "step":
            self.editor.create_step(p)
            return
        self._drawing = self.editor.begin_shape(tool, p)

    def mouseMoveEvent(self, e):
        p = self.mapToScene(e.position().toPoint())
        self.editor.show_cursor_pos(p)
        if self._pan_pos is not None:
            delta = e.position() - self._pan_pos
            self._pan_pos = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        if self._drawing is not None:
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            self.editor.update_shape(self._drawing, self.editor.tool, self._start, p, shift)
            return
        super().mouseMoveEvent(e)
        if self._moves:
            self.editor.position_handles()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._pan_pos is not None:
            self._pan_pos = None
            self.unsetCursor()
            return
        if self._drawing is not None and e.button() == Qt.LeftButton:
            item, self._drawing = self._drawing, None
            self.editor.end_shape(item, self.editor.tool)
            return
        super().mouseReleaseEvent(e)
        if self._moves:
            moved = {it: (old, it.pos()) for it, old in self._moves.items() if it.pos() != old}
            if moved:
                self.editor.push_move(moved)
        self._moves = None

    def keyPressEvent(self, e):
        focus = self.scene().focusItem()
        editing = isinstance(focus, TextItem) and focus.is_editing()
        if not editing:
            if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.editor.delete_selected()
                return
            if e.key() == Qt.Key_Escape:
                self.scene().clearSelection()
                return
            if e.modifiers() == Qt.NoModifier and e.text():
                key = e.text().upper()
                for tool, _label, shortcut in TOOLS:
                    if key == shortcut:
                        self.editor.set_tool(tool)
                        return
            if e.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                step = 10 if e.modifiers() & Qt.ShiftModifier else 1
                dx = {Qt.Key_Left: -step, Qt.Key_Right: step}.get(e.key(), 0)
                dy = {Qt.Key_Up: -step, Qt.Key_Down: step}.get(e.key(), 0)
                items = self.scene().selectedItems()
                if items:
                    self.editor.push_move({it: (it.pos(), it.pos() + QPointF(dx, dy)) for it in items})
                    return
        elif e.key() == Qt.Key_Escape:
            self.scene().clearFocus()
            return
        super().keyPressEvent(e)


class EditorWindow(QMainWindow):
    closed = Signal(object)

    def __init__(self, app, image: QImage, file_path: str | None = None, title_hint: str = ""):
        super().__init__()
        self.app = app
        self.cfg = app.cfg
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowIcon(icons.app_icon())
        self.file_path = file_path
        self.title_hint = title_hint
        self._never_saved = file_path is None
        self._z = 0
        self.tool = "select"

        self.scene = QGraphicsScene(self)
        self.base = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.base.setZValue(-1_000_000)
        self.base.setTransformationMode(Qt.FastTransformation)
        self.scene.addItem(self.base)
        self.scene.setSceneRect(QRectF(self.base.pixmap().rect()))

        self.undo = QUndoStack(self)
        self.undo.cleanChanged.connect(lambda _c: self._update_title())
        self.undo.indexChanged.connect(lambda _i: self.update_handles())
        self._handles: list = []

        self.view = CanvasView(self)
        self.setCentralWidget(self.view)

        self.color = QColor(self.cfg.get("editor_color"))
        self._build_ui()
        self._update_title()
        self._update_status()
        self._initial_size()
        self.scene.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------------ UI
    def _act(self, text, icon_name=None, slot=None, shortcut=None, checkable=False):
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icons.icon(icon_name))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(f"{text} ({QKeySequence(shortcut).toString(QKeySequence.NativeText)})")
        if slot:
            a.triggered.connect(slot)
        a.setCheckable(checkable)
        return a

    def _build_ui(self):
        self.a_open = self._act("Buka…", "open", self.open_file, QKeySequence.Open)
        self.a_save = self._act("Simpan", "save", self.save, QKeySequence.Save)
        self.a_save_as = self._act("Simpan sebagai…", "save_as", self.save_as, "Ctrl+Shift+S")
        self.a_copy = self._act("Salin gambar", "copy", self.copy_to_clipboard, QKeySequence.Copy)
        self.a_print = self._act("Cetak…", "print", self.print_image, QKeySequence.Print)
        self.a_close = self._act("Tutup", None, self.close, QKeySequence.Close)
        self.a_undo = self.undo.createUndoAction(self, "Urungkan")
        self.a_undo.setIcon(icons.icon("undo"))
        self.a_undo.setShortcut(QKeySequence.Undo)
        self.a_redo = self.undo.createRedoAction(self, "Ulangi")
        self.a_redo.setIcon(icons.icon("redo"))
        self.a_redo.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Y")])
        self.a_delete = self._act("Hapus objek (Del)", "delete", self.delete_selected)
        self.a_select_all = self._act("Pilih semua objek", None, self.select_all, QKeySequence.SelectAll)
        self.a_resize = self._act("Ubah ukuran…", "resize", self.resize_image, "Ctrl+R")
        self.a_rot_l = self._act("Putar kiri", "rotate_left", lambda: self.rotate(-90))
        self.a_rot_r = self._act("Putar kanan", "rotate_right", lambda: self.rotate(90))
        self.a_flip_h = self._act("Balik horizontal", "flip_h", lambda: self.flip(True, False))
        self.a_flip_v = self._act("Balik vertikal", "flip_v", lambda: self.flip(False, True))
        self.a_ocr = self._act("OCR: ambil teks dari gambar", "ocr", self.run_ocr, "Ctrl+T")
        self.a_zoom_in = self._act("Perbesar", "zoom_in", lambda: self.view.zoom_by(1.25), QKeySequence.ZoomIn)
        self.a_zoom_out = self._act("Perkecil", "zoom_out", lambda: self.view.zoom_by(0.8), QKeySequence.ZoomOut)
        self.a_zoom_100 = self._act("Ukuran asli (100%)", "zoom_100", lambda: self.view.set_zoom(1.0), "Ctrl+0")
        self.a_zoom_fit = self._act("Sesuaikan jendela", "zoom_fit", self.view.fit, "Ctrl+9")
        for a in (self.a_save, self.a_save_as, self.a_copy, self.a_print, self.a_close, self.a_undo,
                  self.a_redo, self.a_select_all, self.a_resize, self.a_ocr, self.a_zoom_in,
                  self.a_zoom_out, self.a_zoom_100, self.a_zoom_fit, self.a_open):
            self.addAction(a)

        # Main toolbar
        tb = self.addToolBar("Utama")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        for a in (self.a_open, self.a_save, self.a_save_as, self.a_copy, self.a_print):
            tb.addAction(a)
        self.send_menu = self._build_send_menu()
        send_btn = QToolButton()
        send_btn.setIcon(icons.icon("send"))
        send_btn.setText("Kirim")
        send_btn.setToolTip("Kirim / upload / buka dengan…")
        send_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        send_btn.setPopupMode(QToolButton.InstantPopup)
        send_btn.setMenu(self.send_menu)
        tb.addWidget(send_btn)
        tb.addSeparator()
        tb.addAction(self.a_undo)
        tb.addAction(self.a_redo)
        tb.addAction(self.a_delete)
        tb.addSeparator()
        for a in (self.a_resize, self.a_rot_l, self.a_rot_r, self.a_flip_h, self.a_flip_v):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_ocr)
        tb.addSeparator()
        for a in (self.a_zoom_out, self.a_zoom_in, self.a_zoom_100, self.a_zoom_fit):
            tb.addAction(a)

        self.addToolBarBreak()
        # Drawing toolbar
        dt = self.addToolBar("Gambar")
        dt.setObjectName("draw")
        dt.setMovable(False)
        dt.setIconSize(QSize(22, 22))
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for key, label, sc in TOOLS:
            a = QAction(icons.icon(key), label, self)
            a.setCheckable(True)
            a.setToolTip(f"{label} ({sc})")
            a.triggered.connect(lambda _c=False, k=key: self.set_tool(k))
            self.tool_group.addAction(a)
            dt.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions["select"].setChecked(True)
        dt.addSeparator()

        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Warna")
        self.color_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.color_btn.clicked.connect(self.choose_color)
        menu = QMenu(self.color_btn)
        for c in QUICK_COLORS:
            act = menu.addAction(icons.color_swatch_icon(QColor(c)), c)
            act.triggered.connect(lambda _c=False, col=c: self.set_color(QColor(col)))
        menu.addSeparator()
        menu.addAction("Warna lain…", self.choose_color)
        self.color_btn.setMenu(menu)
        dt.addWidget(self.color_btn)

        dt.addWidget(QLabel(" Tebal "))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setValue(self.cfg.get("editor_width"))
        self.width_spin.setToolTip("Ketebalan garis / ukuran blok sensor / ukuran nomor")
        self.width_spin.valueChanged.connect(lambda v: self._style_changed(width=v))
        dt.addWidget(self.width_spin)

        dt.addWidget(QLabel(" Huruf "))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(6, 200)
        self.font_spin.setValue(self.cfg.get("editor_font_size"))
        self.font_spin.setToolTip("Ukuran huruf (px)")
        self.font_spin.valueChanged.connect(lambda v: self._style_changed(font_size=v))
        dt.addWidget(self.font_spin)

        self.fill_check = QCheckBox("Isi")
        self.fill_check.setToolTip("Isi kotak/elips dengan warna (atau latar putih untuk teks)")
        self.fill_check.toggled.connect(lambda v: self._style_changed(fill=v))
        dt.addWidget(self.fill_check)
        self._refresh_color_btn()

        # Menus
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_open, self.a_save, self.a_save_as, None, self.a_copy, self.a_print, None, self.a_close):
            m.addSeparator() if a is None else m.addAction(a)
        send = mb.addMenu("&Kirim")
        for a in self.send_menu.actions():
            send.addAction(a)
        m = mb.addMenu("&Edit")
        for a in (self.a_undo, self.a_redo, None, self.a_delete, self.a_select_all):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Gambar")
        for a in (self.a_resize, self.a_rot_l, self.a_rot_r, self.a_flip_h, self.a_flip_v):
            m.addAction(a)
        m.addSeparator()
        m.addAction("Tambah bingkai/border…", self.add_border)
        m = mb.addMenu("&Tampilan")
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_zoom_100, self.a_zoom_fit):
            m.addAction(a)
        m = mb.addMenu("&Alat")
        m.addAction(self.a_ocr)
        m.addAction("Tangkap baru (area)", lambda: self.app.start_capture("region"))

        sb = self.statusBar()
        self.lbl_size = QLabel()
        self.lbl_zoom = QLabel()
        self.lbl_pos = QLabel()
        sb.addPermanentWidget(self.lbl_pos)
        sb.addPermanentWidget(self.lbl_size)
        sb.addPermanentWidget(self.lbl_zoom)

    def _initial_size(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pm = self.base.pixmap()
        w = min(max(pm.width() + 60, 760), int(screen.width() * 0.88))
        h = min(max(pm.height() + 170, 520), int(screen.height() * 0.88))
        self.resize(w, h)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            vp = self.view.viewport().size()
            pm = self.base.pixmap()
            if pm.width() > vp.width() or pm.height() > vp.height():
                self.view.fit()
            else:
                self.view.set_zoom(1.0)

    # ------------------------------------------------------------ status
    def _update_title(self):
        name = os.path.basename(self.file_path) if self.file_path else (self.title_hint or "Tangkapan baru")
        try:
            dirty = (not self.undo.isClean()) or self._never_saved
        except RuntimeError:  # undo stack destroyed during shutdown
            return
        self.setWindowTitle(f"{'• ' if dirty else ''}{name} - Raja Capture Editor")

    def _update_status(self):
        pm = self.base.pixmap()
        self.lbl_size.setText(f"  {pm.width()} × {pm.height()} px  ")

    def on_zoom_changed(self, z: float):
        self.lbl_zoom.setText(f"  {z * 100:.0f}%  ")

    def show_cursor_pos(self, p: QPointF):
        self.lbl_pos.setText(f"  x {int(p.x())}, y {int(p.y())}  ")

    # ------------------------------------------------------------ style
    def current_style(self) -> dict:
        return {
            "color": QColor(self.color),
            "width": self.width_spin.value(),
            "fill": self.fill_check.isChecked(),
            "font_size": self.font_spin.value(),
        }

    def _refresh_color_btn(self):
        self.color_btn.setIcon(icons.color_swatch_icon(self.color))

    def set_color(self, color: QColor):
        if not color.isValid():
            return
        self.color = QColor(color)
        self.cfg.set("editor_color", self.color.name())
        self._refresh_color_btn()
        self._style_changed(color=QColor(color))

    def choose_color(self):
        c = QColorDialog.getColor(self.color, self, "Pilih warna", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.set_color(c)

    def _style_changed(self, **kw):
        if "width" in kw:
            self.cfg.set("editor_width", kw["width"])
        if "font_size" in kw:
            self.cfg.set("editor_font_size", kw["font_size"])
        items = self.selected_annotations()
        if not items:
            return
        old = {it: it.get_style() for it in items}

        def redo():
            for it in items:
                it.apply_style(**kw)

        def undo():
            for it, s in old.items():
                it.apply_style(**s)

        self.undo.push(FuncCommand("Ubah gaya", redo, undo))

    # ------------------------------------------------------------ resize handles
    def update_handles(self):
        try:
            items = self.selected_annotations()
        except RuntimeError:
            return
        target = items[0] if len(items) == 1 and getattr(items[0], "resizable", False) else None
        current = self._handles[0].target if self._handles else None
        if target is current and target is not None and all(h.scene() for h in self._handles):
            self.position_handles()
            return
        for h in self._handles:
            if h.scene() is not None:
                self.scene.removeItem(h)
        self._handles = []
        if target is None or target.scene() is None:
            return
        for key, pt in target.control_points().items():
            h = HandleItem(target, key, self._push_geometry)
            h.setPos(pt)
            self.scene.addItem(h)
            self._handles.append(h)

    def position_handles(self):
        for h in self._handles:
            h.setPos(h.target.control_points()[h.key])

    def _push_geometry(self, item, old, new):
        if old == new:
            return
        self.undo.push(FuncCommand("Ubah ukuran objek", lambda: item.set_geometry(new),
                                   lambda: item.set_geometry(old)))

    def _on_selection(self):
        self.update_handles()
        items = self.selected_annotations()
        if len(items) == 1:
            s = items[0].get_style()
            for w, v in ((self.width_spin, int(s["width"])), (self.font_spin, int(s["font_size"]))):
                w.blockSignals(True)
                w.setValue(v)
                w.blockSignals(False)
            self.fill_check.blockSignals(True)
            self.fill_check.setChecked(bool(s["fill"]))
            self.fill_check.blockSignals(False)

    # ------------------------------------------------------------ tools
    def set_tool(self, tool: str):
        self.tool = tool
        self.tool_actions[tool].setChecked(True)
        self.view.setCursor(Qt.ArrowCursor if tool == "select" else
                            (Qt.IBeamCursor if tool == "text" else Qt.CrossCursor))
        if tool != "select":
            self.scene.clearSelection()

    def _next_z(self) -> int:
        self._z += 1
        return self._z

    def annotations(self) -> list:
        return [it for it in self.scene.items() if isinstance(it, Annotation)]

    def selected_annotations(self) -> list:
        return [it for it in self.scene.selectedItems() if isinstance(it, Annotation)]

    def begin_shape(self, tool: str, p: QPointF):
        s = self.current_style()
        r = QRectF(p, p)
        if tool == "rect":
            item = RectItem(r, **s)
        elif tool == "ellipse":
            item = EllipseItem(r, **s)
        elif tool == "highlight":
            s["color"] = HIGHLIGHT_YELLOW
            item = HighlightItem(r, **s)
        elif tool == "pixelate":
            item = PixelateItem(r, self.base, **s)
        elif tool == "line":
            item = LineItem(QLineF(p, p), **s)
        elif tool == "arrow":
            item = ArrowItem(QLineF(p, p), **s)
        elif tool == "pen":
            item = PenItem(p, **s)
        elif tool == "crop":
            item = QGraphicsRectItem(r)
            pen = QPen(QColor(0, 160, 255), 1.5, Qt.DashLine)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(QColor(0, 160, 255, 40))
        else:
            return None
        item.setZValue(1_000_000 if tool == "crop" else self._next_z())
        self.scene.addItem(item)
        return item

    def update_shape(self, item, tool: str, start: QPointF, p: QPointF, shift: bool):
        if item is None:
            return
        if tool in ("rect", "ellipse", "highlight", "pixelate", "crop"):
            if shift:
                p = _square(start, p)
            if tool == "crop":
                p = QPointF(min(max(p.x(), 0), self.scene.sceneRect().width()),
                            min(max(p.y(), 0), self.scene.sceneRect().height()))
            item.setRect(QRectF(start, p).normalized())
        elif tool in ("line", "arrow"):
            if shift:
                p = _snap45(start, p)
            item.setLine(QLineF(start, p))
        elif tool == "pen":
            path = item.path()
            path.lineTo(p)
            item.setPath(path)

    def end_shape(self, item, tool: str):
        if item is None:
            return
        if tool == "crop":
            r = item.rect()
            self.scene.removeItem(item)
            if r.width() >= 2 and r.height() >= 2:
                self.crop(r)
                self.set_tool("select")
            return
        br = item.boundingRect()
        too_small = False
        if tool in ("line", "arrow"):
            too_small = item.line().length() < 3
        elif tool in ("rect", "ellipse", "highlight", "pixelate"):
            too_small = item.rect().width() < 3 and item.rect().height() < 3
        elif tool == "pen":
            too_small = br.width() < 1 and br.height() < 1
        if too_small:
            self.scene.removeItem(item)
            return
        self._push_add(item, "Tambah objek")

    def _push_add(self, item, text):
        def redo():
            if item.scene() is None:
                self.scene.addItem(item)

        def undo():
            if item.scene() is not None:
                self.scene.removeItem(item)

        self.undo.push(FuncCommand(text, redo, undo))

    def create_text(self, p: QPointF):
        item = TextItem(p, **self.current_style())
        item.setZValue(self._next_z())
        item.on_edit_done = self._text_done
        self.scene.addItem(item)
        item._pending = True
        item.start_edit()

    def _text_done(self, item: TextItem):
        empty = not item.toPlainText().strip()
        if getattr(item, "_pending", False):
            item._pending = False
            if empty:
                self.scene.removeItem(item)
            else:
                self._push_add(item, "Tambah teks")
        elif empty and item.scene() is not None:
            self.scene.clearSelection()
            item.setSelected(True)
            self.delete_selected()

    def create_step(self, p: QPointF):
        numbers = [it.number for it in self.scene.items() if isinstance(it, StepItem)]
        item = StepItem(p, (max(numbers) + 1) if numbers else 1, **self.current_style())
        item.setZValue(self._next_z())
        self.scene.addItem(item)
        self._push_add(item, "Tambah nomor")

    def push_move(self, moved: dict):
        """moved: {item: (old_pos, new_pos)}. push() runs redo(), which applies new_pos
        (a no-op when the item was already dragged there)."""

        def redo():
            for it, (_old, new) in moved.items():
                it.setPos(new)

        def undo():
            for it, (old, _new) in moved.items():
                it.setPos(old)

        self.undo.push(FuncCommand("Pindahkan", redo, undo))

    def delete_selected(self):
        items = self.selected_annotations()
        if not items:
            return

        def redo():
            for it in items:
                if it.scene() is not None:
                    self.scene.removeItem(it)

        def undo():
            for it in items:
                if it.scene() is None:
                    self.scene.addItem(it)

        self.undo.push(FuncCommand("Hapus", redo, undo))

    def select_all(self):
        for it in self.annotations():
            it.setSelected(True)

    # ------------------------------------------------------------ image ops
    def _finish_text_edit(self):
        focus = self.scene.focusItem()
        if focus is not None:
            self.scene.clearFocus()

    def crop(self, rect: QRectF):
        self._finish_text_edit()
        r = rect.toAlignedRect().intersected(self.base.pixmap().rect())
        if r.width() < 1 or r.height() < 1:
            return
        old_pm = self.base.pixmap()
        new_pm = old_pm.copy(r)
        items = self.annotations()
        dx, dy = r.x(), r.y()

        def redo():
            self.base.setPixmap(new_pm)
            for it in items:
                it.moveBy(-dx, -dy)
            self.scene.setSceneRect(QRectF(new_pm.rect()))
            self._update_status()

        def undo():
            self.base.setPixmap(old_pm)
            for it in items:
                it.moveBy(dx, dy)
            self.scene.setSceneRect(QRectF(old_pm.rect()))
            self._update_status()

        self.undo.push(FuncCommand("Potong", redo, undo))

    def _flatten_transform(self, text: str, fn):
        self._finish_text_edit()
        new_img = fn(self.render_image())
        old_pm = self.base.pixmap()
        new_pm = QPixmap.fromImage(new_img)
        items = self.annotations()

        def redo():
            for it in items:
                if it.scene() is not None:
                    self.scene.removeItem(it)
            self.base.setPixmap(new_pm)
            self.scene.setSceneRect(QRectF(new_pm.rect()))
            self._update_status()

        def undo():
            self.base.setPixmap(old_pm)
            for it in items:
                if it.scene() is None:
                    self.scene.addItem(it)
            self.scene.setSceneRect(QRectF(old_pm.rect()))
            self._update_status()

        self.undo.push(FuncCommand(text, redo, undo))

    def resize_image(self):
        pm = self.base.pixmap()
        dlg = ResizeDialog(pm.width(), pm.height(), self)
        if dlg.exec():
            w, h = dlg.size_value()
            if (w, h) != (pm.width(), pm.height()):
                self._flatten_transform("Ubah ukuran", lambda img: img.scaled(
                    w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

    def rotate(self, degrees: int):
        self._flatten_transform("Putar", lambda img: img.transformed(QTransform().rotate(degrees),
                                                                        Qt.SmoothTransformation))

    def flip(self, horizontal: bool, vertical: bool):
        self._flatten_transform("Balik", lambda img: img.mirrored(horizontal, vertical))

    def add_border(self):
        from PySide6.QtWidgets import QInputDialog

        size, ok = QInputDialog.getInt(self, "Bingkai", "Tebal bingkai (px):", 4, 1, 200)
        if not ok:
            return
        color = QColor(self.color)

        def fn(img: QImage) -> QImage:
            out = QImage(img.width() + 2 * size, img.height() + 2 * size, QImage.Format_ARGB32)
            out.fill(color)
            p = QPainter(out)
            p.drawImage(size, size, img)
            p.end()
            return out

        self._flatten_transform("Bingkai", fn)

    # ------------------------------------------------------------ export
    def render_image(self) -> QImage:
        selected = self.scene.selectedItems()
        self.scene.clearSelection()
        r = self.scene.sceneRect()
        img = QImage(int(r.width()), int(r.height()), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self.scene.render(p, QRectF(img.rect()), r)
        p.end()
        for it in selected:
            it.setSelected(True)
        return img

    def _write(self, path: str) -> bool:
        self._finish_text_edit()
        ok = save_image(self.render_image(), path, self.cfg.get("jpeg_quality"))
        if not ok:
            QMessageBox.critical(self, "Gagal menyimpan", f"Tidak bisa menyimpan ke:\n{path}")
            return False
        self.file_path = path
        self._never_saved = False
        self.undo.setClean()
        self._update_title()
        self.statusBar().showMessage(f"Tersimpan: {path}", 5000)
        return True

    def save(self) -> bool:
        if self.file_path and os.path.splitext(self.file_path)[1].lower() != ".pdf":
            return self._write(self.file_path)
        return self.save_as()

    def save_as(self) -> bool:
        fmt = self.cfg.get("image_format")
        if self.file_path:
            default = self.file_path
        else:
            default = next_filename(self.cfg.get("output_dir"), self.cfg.get("filename_pattern"), fmt)
        selected = {"png": "PNG (*.png)", "jpg": "JPEG (*.jpg *.jpeg)", "bmp": "BMP (*.bmp)",
                    "webp": "WEBP (*.webp)"}.get(fmt, "PNG (*.png)")
        path, chosen = QFileDialog.getSaveFileName(self, "Simpan gambar", default, SAVE_FILTER, selected)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            ext = {"PNG": ".png", "JPEG": ".jpg", "BMP": ".bmp", "WEBP": ".webp", "PDF": ".pdf"}.get(
                chosen.split(" ")[0], ".png")
            path += ext
        return self._write(path)

    def copy_to_clipboard(self):
        focus = self.scene.focusItem()
        if isinstance(focus, TextItem) and focus.is_editing():
            QGuiApplication.clipboard().setText(focus.textCursor().selectedText())
            return
        QGuiApplication.clipboard().setImage(self.render_image())
        self.statusBar().showMessage("Gambar disalin ke clipboard", 3000)

    def print_image(self):
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(self, "Cetak", "Modul QtPrintSupport tidak tersedia.")
            return
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        img = self.render_image()
        p = QPainter(printer)
        page = printer.pageRect(QPrinter.DevicePixel).toRect()
        size = img.size().scaled(page.size(), Qt.KeepAspectRatio)
        if img.width() <= page.width() and img.height() <= page.height():
            size = img.size()
        p.drawImage(QRectF(0, 0, size.width(), size.height()), img)
        p.end()

    # ------------------------------------------------------------ send / share
    def _build_send_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction(icons.icon("upload"), "Upload ke Imgur", lambda: self.upload("imgur"))
        m.addAction(icons.icon("upload"), "Upload ke server kustom", lambda: self.upload("custom"))
        m.addAction("Riwayat upload…", lambda: self.app.show_upload_history())
        m.addSeparator()
        m.addAction("Kirim lewat email (lampiran)", self.send_email)
        m.addAction(icons.icon("copy"), "Salin sebagai file", self.copy_as_file)
        m.addSeparator()
        self.open_with_menu = m.addMenu("Buka dengan")
        self.open_with_menu.aboutToShow.connect(self._fill_open_with)
        m.addAction(icons.icon("open"), "Tampilkan di folder", self.reveal)
        return m

    def share_file(self) -> str:
        """Current image (with annotations) written to a temp PNG for sharing."""
        from ..share import share_dir

        self._finish_text_edit()
        path = next_filename(share_dir(), self.cfg.get("filename_pattern"), "png")
        if not save_image(self.render_image(), path):
            raise OSError(f"Gagal menulis {path}")
        return path

    def upload(self, service: str):
        from .. import share
        from .dialogs import UploadResultDialog

        if service == "imgur" and not self.cfg.get("imgur_confirmed"):
            res = QMessageBox.question(
                self, "Upload ke Imgur",
                "Gambar akan diunggah ke Imgur dan bisa dilihat siapa pun yang punya link-nya.\n"
                "Lanjutkan? (pertanyaan ini tidak akan muncul lagi)")
            if res != QMessageBox.Yes:
                return
            self.cfg.set("imgur_confirmed", True)
        path = self.share_file()
        cfg = self.cfg
        if service == "imgur":
            fn, args = share.upload_imgur, (path, cfg.get("imgur_client_id"))
        else:
            fn, args = share.upload_custom, (path, cfg.get("custom_upload_url"), cfg.get("custom_upload_field"),
                                             cfg.get("custom_upload_headers"), cfg.get("custom_upload_response"))
        self.statusBar().showMessage("Mengunggah…")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

        def done(result):
            QGuiApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Upload selesai, link disalin", 5000)
            share.add_history(cfg, result)
            UploadResultDialog(result, self).show()

        def fail(exc):
            QGuiApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "Upload gagal", str(exc))

        run_async(fn, *args, on_done=done, on_error=fail)

    def send_email(self):
        from ..share import email_with_attachment

        self.statusBar().showMessage(email_with_attachment(self.share_file()), 6000)

    def copy_as_file(self):
        from ..share import copy_file_to_clipboard

        copy_file_to_clipboard(self.share_file())
        self.statusBar().showMessage("File disalin - tempel di aplikasi chat atau file manager", 5000)

    def reveal(self):
        from ..share import reveal_in_folder

        if self.file_path and os.path.exists(self.file_path):
            reveal_in_folder(self.file_path)
        else:
            reveal_in_folder(self.share_file())

    def _fill_open_with(self):
        from ..share import external_programs

        m = self.open_with_menu
        m.clear()
        m.addAction("Aplikasi bawaan sistem", self._open_default)
        progs = external_programs(self.cfg)
        if progs:
            m.addSeparator()
        for prog in progs:
            m.addAction(os.path.basename(prog), lambda p=prog: self._open_with(p))
        m.addSeparator()
        m.addAction("Pilih program…", self._choose_program)

    def _open_default(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(self.share_file()))

    def _open_with(self, program: str):
        from ..share import open_with, remember_program

        try:
            open_with(program, self.share_file())
            remember_program(self.cfg, program)
        except OSError as exc:
            QMessageBox.warning(self, "Buka dengan", f"Gagal menjalankan {program}:\n{exc}")

    def _choose_program(self):
        start = "/usr/bin" if os.path.isdir("/usr/bin") else ""
        prog, _ = QFileDialog.getOpenFileName(self, "Pilih program (mis. GIMP)", start)
        if prog:
            self._open_with(prog)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Buka gambar", self.cfg.get("output_dir"), OPEN_FILTER)
        if path:
            self.app.open_image_file(path)

    # ------------------------------------------------------------ OCR
    def run_ocr(self):
        from ..ocr import find_tesseract, run_ocr

        img = self.render_image()
        sel = self.scene.selectedItems()
        if len(sel) == 1 and isinstance(sel[0], (RectItem, HighlightItem)):
            img = img.copy(sel[0].sceneBoundingRect().toAlignedRect())
        exe = find_tesseract(self.cfg.get("tesseract_path"))
        self.statusBar().showMessage("Menjalankan OCR…")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

        def done(text):
            QGuiApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()
            TextResultDialog(text, parent=self).exec()

        def fail(exc):
            QGuiApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "OCR gagal", str(exc))

        run_async(run_ocr, img, self.cfg.get("ocr_lang"), exe, on_done=done, on_error=fail)

    # ------------------------------------------------------------ close
    def closeEvent(self, e):
        if self._never_saved or not self.undo.isClean():
            res = QMessageBox.question(
                self, "Simpan perubahan?", "Gambar ini belum disimpan. Simpan sebelum menutup?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if res == QMessageBox.Cancel or (res == QMessageBox.Save and not self.save()):
                e.ignore()
                return
        self.closed.emit(self)
        super().closeEvent(e)


__all__ = ["EditorWindow", "QWidget"]
