"""Render marketing screenshots of the real UI onto a synthetic desktop.

    QT_QPA_PLATFORM=offscreen python packaging/make_screenshots.py

Writes PNGs to docs/assets/. No real screen content is captured.
"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="raja-shots-")  # never touch user settings

from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "assets")


def fake_desktop(w=1280, h=800) -> QImage:
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#24305e"))
    g.setColorAt(1, QColor("#5b3a8c"))
    p.fillRect(img.rect(), g)
    # top bar
    p.fillRect(0, 0, w, 28, QColor(10, 10, 16, 230))
    p.setPen(QColor("#ddd"))
    f = QFont()
    f.setPixelSize(13)
    p.setFont(f)
    p.drawText(QRect(0, 0, w, 28), Qt.AlignCenter, "Sel 17 Nov  13:34")
    # browser-like window
    win = QRectF(90, 70, 820, 560)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawRoundedRect(win.translated(0, 8), 12, 12)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(win, 12, 12)
    p.setBrush(QColor("#eef1f6"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(win.x(), win.y(), win.width(), 44), 12, 12)
    p.drawPath(path)
    p.fillRect(QRectF(win.x(), win.y() + 30, win.width(), 14), QColor("#eef1f6"))
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        p.setBrush(QColor(c))
        p.drawEllipse(QPointF(win.x() + 22 + i * 20, win.y() + 22), 6, 6)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(win.x() + 100, win.y() + 10, 520, 24), 12, 12)
    p.setPen(QColor("#667"))
    p.drawText(QRectF(win.x() + 116, win.y() + 10, 500, 24), Qt.AlignVCenter, "dashboard.tokoraja.id/penjualan")
    # page content
    x0, y0 = win.x() + 36, win.y() + 76
    f.setPixelSize(24)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1d2433"))
    p.drawText(QPointF(x0, y0 + 10), "Laporan Penjualan Q4")
    f.setPixelSize(13)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#6b7280"))
    p.drawText(QPointF(x0, y0 + 36), "Ringkasan performa toko per kategori produk")
    cards = [("Pendapatan", "Rp 482,7 jt", "#1e88e5"), ("Pesanan", "12.408", "#43a047"),
             ("Pelanggan baru", "3.215", "#fb8c00")]
    for i, (label, val, col) in enumerate(cards):
        r = QRectF(x0 + i * 250, y0 + 60, 230, 86)
        p.setPen(QPen(QColor("#e5e7eb"), 1))
        p.setBrush(QColor("#fafbfc"))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(QColor("#6b7280"))
        p.drawText(r.adjusted(16, 14, 0, 0), Qt.AlignLeft | Qt.AlignTop, label)
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(col))
        p.drawText(r.adjusted(16, 38, 0, 0), Qt.AlignLeft | Qt.AlignTop, val)
        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
    # bar chart
    chart = QRectF(x0, y0 + 170, 480, 250)
    p.setPen(QPen(QColor("#e5e7eb"), 1))
    for k in range(5):
        y = chart.bottom() - k * chart.height() / 4
        p.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
    vals = [0.42, 0.58, 0.51, 0.74, 0.66, 0.88, 0.79]
    bw = chart.width() / len(vals)
    for i, v in enumerate(vals):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1e88e5") if i != 5 else QColor("#3949ab"))
        p.drawRoundedRect(QRectF(chart.left() + i * bw + 12, chart.bottom() - v * chart.height(),
                                 bw - 24, v * chart.height()), 4, 4)
    # table-ish list
    p.setPen(QColor("#374151"))
    rows = [("Elektronik", "Rp 182 jt"), ("Fashion", "Rp 121 jt"), ("Rumah tangga", "Rp 96 jt"),
            ("Kecantikan", "Rp 54 jt"), ("Olahraga", "Rp 29 jt")]
    for i, (a, b) in enumerate(rows):
        y = chart.top() + 10 + i * 46
        p.setPen(QPen(QColor("#eef0f3"), 1))
        p.drawLine(QPointF(x0 + 520, y + 30), QPointF(x0 + 740, y + 30))
        p.setPen(QColor("#374151"))
        p.drawText(QPointF(x0 + 520, y + 18), a)
        p.drawText(QRectF(x0 + 600, y, 140, 24), Qt.AlignRight | Qt.AlignVCenter, b)
    # chat window
    chat = QRectF(950, 140, 290, 380)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawRoundedRect(chat.translated(0, 8), 12, 12)
    p.setBrush(QColor("#f7f7fb"))
    p.drawRoundedRect(chat, 12, 12)
    p.setPen(QColor("#1d2433"))
    f.setBold(True)
    p.setFont(f)
    p.drawText(chat.adjusted(16, 14, 0, 0), Qt.AlignLeft | Qt.AlignTop, "Tim Marketing")
    f.setBold(False)
    p.setFont(f)
    bubbles = [(False, "Sudah ada data Q4?"), (True, "Sudah, saya kirim screenshot ya"),
               (False, "Tolong tandai yang naik 👍")]
    for i, (me, text) in enumerate(bubbles):
        bw2 = p.fontMetrics().horizontalAdvance(text) + 24
        r = QRectF(chat.right() - bw2 - 14 if me else chat.left() + 14, chat.top() + 56 + i * 52, bw2, 36)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1e88e5") if me else QColor("#e6e8ef"))
        p.drawRoundedRect(r, 16, 16)
        p.setPen(Qt.white if me else QColor("#1d2433"))
        p.drawText(r, Qt.AlignCenter, text)
    p.end()
    return img


def main():
    app = QApplication(sys.argv[:1])
    os.makedirs(OUT, exist_ok=True)
    from raja_capture.app import RajaApp
    from raja_capture.capture.base import DesktopShot
    from raja_capture.ui.editor import EditorWindow
    from raja_capture.ui.items import ArrowItem, HighlightItem, PixelateItem, RectItem, StepItem, TextItem
    from raja_capture.ui.overlay import OverlayController

    raja = RajaApp(app)
    desk = fake_desktop()

    # 1) toolbar
    raja.toolbar.show()
    app.processEvents()
    raja.toolbar.grab().save(os.path.join(OUT, "toolbar.png"))
    raja.toolbar.hide()

    # 2) region selection overlay (magnifier + size label)
    shot = DesktopShot(desk, QRect(0, 0, desk.width(), desk.height()))
    ctrl = OverlayController(shot, "region")
    ov = ctrl.overlays[0]
    ov.geo = QRect(0, 0, desk.width(), desk.height())
    ov.img_rect = QRect(0, 0, desk.width(), desk.height())
    ov.sub = desk
    ov.sx = ov.sy = 1.0
    from PySide6.QtGui import QPixmap

    ov.pix = QPixmap.fromImage(desk)
    ov.resize(desk.size())
    ov.origin, ov.cur, ov.mouse = QPoint(110, 130), QPoint(640, 470), QPoint(640, 470)
    ov.grab().save(os.path.join(OUT, "select.png"))
    ctrl.cancel()

    # 3) editor with annotations
    crop = desk.copy(QRect(90, 70, 820, 560))
    ed = EditorWindow(raja, crop, title_hint="Laporan Penjualan")
    ed.resize(1120, 760)
    ed.show()
    style = dict(color=QColor("#e53935"), width=4)
    items = [
        RectItem(QRectF(30, 120, 240, 100), **style),
        ArrowItem(QLineF(520, 140, 410, 330), **style),
        HighlightItem(QRectF(34, 60, 330, 28)),
        PixelateItem(QRectF(536, 220, 250, 230), ed.base, width=4),
        StepItem(QPointF(30, 120), 1, **style),
        StepItem(QPointF(358, 330), 2, **style),
    ]
    text = TextItem(QPointF(470, 96), color=QColor("#e53935"), font_size=22, fill=True)
    text.setPlainText("Naik 18% 🚀")
    items.append(text)
    for z, it in enumerate(items):
        it.setZValue(z + 1)
        ed.scene.addItem(it)
    ed.set_tool("arrow")
    items[1].setSelected(True)
    app.processEvents()
    ed.view.set_zoom(1.0)
    ed.view.centerOn(ed.scene.sceneRect().center())
    app.processEvents()
    ed.grab().save(os.path.join(OUT, "editor.png"))
    ed._never_saved = False
    ed.undo.setClean()
    ed.close()
    print("screenshots ->", OUT)
    os._exit(0)  # avoid PySide teardown order issues


if __name__ == "__main__":
    main()
