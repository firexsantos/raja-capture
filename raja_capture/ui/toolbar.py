"""Small floating capture panel (like FastStone's capture bar)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

from ..config import ACTION_LABELS, AFTER_CAPTURE
from ..util import is_wayland
from . import icons

DELAYS = [(0, "Tanpa jeda"), (3, "Jeda 3 dtk"), (5, "Jeda 5 dtk"), (10, "Jeda 10 dtk")]


class CaptureToolbar(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.app = app
        self.setWindowTitle("Raja Capture")
        self.setWindowIcon(icons.app_icon())
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(1)

        def hk(action):
            seq = app.cfg.hotkey(action)
            return f" ({QKeySequence(seq).toString(QKeySequence.NativeText)})" if seq else ""

        def button(icon_name, tip, slot):
            b = QToolButton()
            b.setIcon(icons.icon(icon_name))
            b.setIconSize(QSize(26, 26))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        for action, icon_name in (("full", "full"), ("window", "window"), ("region", "region"),
                                  ("scroll", "scroll")):
            button(icon_name, ACTION_LABELS[action] + hk(action),
                   lambda _=False, a=action: app.start_capture(a))

        self.rec_btn = QToolButton()
        self.rec_btn.setIcon(icons.icon("record"))
        self.rec_btn.setIconSize(QSize(26, 26))
        self.rec_btn.setAutoRaise(True)
        self.rec_btn.setPopupMode(QToolButton.InstantPopup)
        self.rec_btn.setToolTip("Rekam layar")
        self.rec_menu = QMenu(self.rec_btn)
        self.rec_menu.addAction(icons.icon("region"), ACTION_LABELS["record_region"] + hk("record_region"),
                                lambda: app.start_capture("record_region"))
        full_label = "Rekam layar / jendela (pilih)" if is_wayland() else ACTION_LABELS["record_full"]
        self.rec_menu.addAction(icons.icon("full"), full_label + hk("record_full"),
                                lambda: app.start_capture("record_full"))
        self.rec_btn.setMenu(self.rec_menu)
        lay.addWidget(self.rec_btn)

        for action, icon_name in (("color", "color"), ("ruler", "ruler"), ("ocr", "ocr")):
            button(icon_name, ACTION_LABELS[action] + hk(action),
                   lambda _=False, a=action: app.start_capture(a))

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)
        button("open", "Buka gambar di editor", app.open_image_dialog)

        self.delay = QComboBox()
        for sec, label in DELAYS:
            self.delay.addItem(label, sec)
        idx = max(0, self.delay.findData(app.cfg.get("delay")))
        self.delay.setCurrentIndex(idx)
        self.delay.setToolTip("Jeda sebelum menangkap (untuk menu/tooltip)")
        self.delay.currentIndexChanged.connect(lambda _i: app.cfg.set("delay", self.delay.currentData()))
        lay.addWidget(self.delay)

        out = QToolButton()
        out.setText("Output")
        out.setToolTip("Tindakan setelah menangkap")
        out.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(out)
        group = QActionGroup(menu)
        current = app.cfg.get("after_capture")
        for key, label in AFTER_CAPTURE:
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == current)
            a.triggered.connect(lambda _c=False, k=key: app.cfg.set("after_capture", k))
            group.addAction(a)
        out.setMenu(menu)
        lay.addWidget(out)

        button("settings", "Pengaturan", app.show_settings)
        self.setFixedSize(self.sizeHint())

    def set_recording(self, recording: bool):
        if recording:
            self.rec_btn.setIcon(icons.icon("stop"))
            self.rec_btn.setToolTip("Hentikan rekaman")
            self.rec_btn.setMenu(None)
            self.rec_btn.setPopupMode(QToolButton.DelayedPopup)
            try:
                self.rec_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.rec_btn.clicked.connect(self.app.stop_recording)
        else:
            try:
                self.rec_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.rec_btn.setIcon(icons.icon("record"))
            self.rec_btn.setToolTip("Rekam layar")
            self.rec_btn.setMenu(self.rec_menu)
            self.rec_btn.setPopupMode(QToolButton.InstantPopup)

    def closeEvent(self, e):
        if self.app.tray_available():
            e.ignore()
            self.hide()
            self.app.notify_once("tray_hint", "Raja Capture tetap berjalan di tray. "
                                 "Klik ikon tray untuk menampilkan toolbar.")
        else:
            e.accept()
            self.app.quit()
