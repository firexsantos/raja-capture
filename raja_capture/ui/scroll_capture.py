"""Scrolling capture: repeatedly grab a region while the content scrolls, then stitch."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..stitch import Stitcher
from ..util import array_to_qimage, qimage_to_array
from . import icons


class ScrollPanel(QWidget):
    def __init__(self, can_auto: bool):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Raja Capture - Tangkap scroll")
        self.setWindowIcon(icons.app_icon())
        self.info = QLabel("Siap. Tekan Mulai, lalu scroll konten di area terpilih ke bawah.")
        self.info.setWordWrap(True)
        self.preview = QLabel()
        self.preview.setFixedSize(120, 160)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#333; border:1px solid #555;")
        self.auto = QCheckBox("Scroll otomatis")
        self.auto.setVisible(can_auto)
        self.auto.setToolTip("Raja Capture mengirim scroll mouse ke area terpilih secara otomatis")
        self.btn_start = QPushButton("Mulai")
        self.btn_done = QPushButton("Selesai")
        self.btn_cancel = QPushButton("Batal")
        self.btn_done.setEnabled(False)
        right = QVBoxLayout()
        right.addWidget(self.info)
        right.addWidget(self.auto)
        right.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_done)
        row.addWidget(self.btn_cancel)
        right.addLayout(row)
        lay = QHBoxLayout(self)
        lay.addWidget(self.preview)
        lay.addLayout(right, 1)
        self.setFixedWidth(430)
        self.on_close = None

    def set_preview(self, img: QImage):
        pm = QPixmap.fromImage(img).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)

    def closeEvent(self, e):
        if self.on_close:
            self.on_close()
        super().closeEvent(e)


class ScrollCaptureSession(QObject):
    finished = Signal(QImage)
    cancelled = Signal()

    def __init__(self, app, logical_rect: QRect, screen, first_shot):
        super().__init__()
        self.app = app
        self.backend = app.backend
        self.rect = QRect(logical_rect)
        self.screen = screen
        self.stitcher = Stitcher()
        self.running = False
        self.busy = False
        self.same_count = 0
        self._ended = False
        self.panel = ScrollPanel(self.backend.can_auto_scroll)
        self.panel.auto.setChecked(app.cfg.get("scroll_auto"))
        self.panel.btn_start.clicked.connect(self.toggle)
        self.panel.btn_done.clicked.connect(self.finish)
        self.panel.btn_cancel.clicked.connect(self.cancel)
        self.panel.on_close = self.cancel
        self.timer = QTimer(self)
        self.timer.setInterval(max(250, app.cfg.get("scroll_interval_ms")))
        self.timer.timeout.connect(self._tick)
        self._add_frame(first_shot.crop_logical(self.rect))

    def show(self):
        self.panel.adjustSize()
        # Place the panel beside the region so it is not captured (no effect on Wayland).
        avail = self.screen.availableGeometry() if self.screen else None
        if avail is not None:
            x = self.rect.right() + 12
            if x + self.panel.width() > avail.right():
                x = self.rect.left() - self.panel.width() - 12
            x = max(avail.left(), x)
            y = min(max(avail.top(), self.rect.top()), avail.bottom() - self.panel.height())
            self.panel.move(x, y)
        self.panel.show()

    def toggle(self):
        if self.running:
            self.running = False
            self.timer.stop()
            self.panel.btn_start.setText("Lanjut")
            self.panel.info.setText(f"Dijeda. {self._summary()}")
        else:
            self.running = True
            self.app.cfg.set("scroll_auto", self.panel.auto.isChecked())
            self.panel.btn_start.setText("Jeda")
            self.panel.btn_done.setEnabled(True)
            self.panel.info.setText("Merekam… scroll konten ke bawah perlahan.")
            self.timer.start()
            if self._auto():
                self._scroll()

    def _auto(self) -> bool:
        return self.backend.can_auto_scroll and self.panel.auto.isChecked()

    def _scroll(self):
        c = self.rect.center()
        try:
            self.backend.scroll(c.x(), c.y(), -3)
        except Exception:  # noqa: BLE001
            self.panel.auto.setChecked(False)

    def _summary(self) -> str:
        return f"{self.stitcher.frames} frame, tinggi {self.stitcher.height} px."

    def _tick(self):
        if self.busy or not self.running:
            return
        self.busy = True
        self.backend.grab_async(self._on_shot, self._on_error)

    def _on_shot(self, shot):
        self.busy = False
        if self._ended or not self.running:
            return
        status = self._add_frame(shot.crop_logical(self.rect))
        if status == "same":
            self.same_count += 1
            if self._auto() and self.same_count >= 3:
                self.finish()  # reached the end of the page
                return
        else:
            self.same_count = 0
        msg = self._summary()
        if status == "nomatch":
            msg += "  ⚠ Scroll terlalu cepat - scroll lebih pelan."
        self.panel.info.setText(msg)
        if self._auto():
            self._scroll()

    def _on_error(self, exc):
        self.busy = False
        self.panel.info.setText(f"Gagal mengambil gambar: {exc}")

    def _add_frame(self, img: QImage) -> str:
        status = self.stitcher.add(qimage_to_array(img))
        if status == "added":
            res = self.stitcher.result()
            if res is not None:
                self.panel.set_preview(array_to_qimage(res))
        return status

    def _end(self):
        self._ended = True
        self.running = False
        self.timer.stop()
        self.panel.on_close = None
        self.panel.close()
        self.panel.deleteLater()

    def finish(self):
        if self._ended:
            return
        res = self.stitcher.result()
        self._end()
        if res is None:
            self.cancelled.emit()
        else:
            self.finished.emit(array_to_qimage(res))

    def cancel(self):
        if self._ended:
            return
        self._end()
        self.cancelled.emit()
