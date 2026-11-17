"""Scrolling capture: scroll the content, grab the region, stitch - repeat until the end.

Auto-scroll backends:
* Windows / X11 : synthetic mouse wheel at the region (QtBackend.scroll)
* Wayland       : RemoteDesktop portal (one-time GNOME consent, remembered)
Without auto-scroll the user scrolls by hand and capture stops when scrolling stops.

The control panel is hidden while capturing whenever it could overlap the region
(always on Wayland, where windows cannot be positioned), so it never ends up in frames.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..stitch import Stitcher
from ..util import array_to_qimage, is_wayland, qimage_to_array, run_async
from . import icons

SETTLE_MS = 450  # wait for smooth-scroll animations before grabbing
MAX_HEIGHT = 40_000
MANUAL_IDLE_STOP_S = 5.0  # manual mode: stop after this long without movement
MANUAL_START_TIMEOUT_S = 25.0
MAX_FRAMES = 200
MAX_SECONDS = 240
MAX_FAILED_IN_A_ROW = 4  # auto mode: frames that never line up -> stop


# --------------------------------------------------------------------------- scrollers


class QtScroller:
    """Windows / X11: warp the pointer to the region and send wheel clicks."""

    def __init__(self, backend, rect: QRect):
        self.backend, self.rect = backend, rect

    def prepare(self, on_ready, on_fail):
        on_ready()

    def scroll(self, steps: int):
        c = self.rect.center()
        self.backend.scroll(c.x(), self.rect.top() + max(10, self.rect.height() // 8), -steps)

    def close(self):
        pass


class PortalScroller:
    """Wayland: RemoteDesktop portal session (pointer motion + discrete wheel)."""

    def __init__(self, cfg, rect: QRect, screen):
        self.cfg, self.rect, self.screen = cfg, rect, screen
        self.session = None

    def prepare(self, on_ready, on_fail):
        run_async(self._start, on_done=lambda _r: on_ready(), on_error=on_fail)

    def _start(self):
        from ..capture.portal import RemoteDesktopSession

        sess = RemoteDesktopSession()
        try:
            stream = sess.start(self.cfg.get("remote_token") or None)
        except BaseException:
            sess.close()
            self.cfg.set("remote_token", "")
            raise
        if sess.restore_token:
            self.cfg.set("remote_token", sess.restore_token)
        self.session = sess
        # Pointer near the top-centre of the region: wheel events go to the content
        # and the cursor never lands in the newly revealed strips at the bottom.
        x = self.rect.center().x()
        y = self.rect.top() + max(10, self.rect.height() // 8)
        if stream:
            props = stream[1]
            pos = props.get("position")
            if pos:
                x, y = x - pos[0], y - pos[1]
            elif self.screen is not None:
                g = self.screen.geometry()
                x, y = x - g.x(), y - g.y()
            size = props.get("size")
            if size:
                x = min(max(x, 0), size[0] - 1)
                y = min(max(y, 0), size[1] - 1)
            try:
                sess.move_pointer(x, y)
            except Exception:  # noqa: BLE001 - scrolling still works where the pointer is
                pass
        return True

    def scroll(self, steps: int):
        if self.session is not None:
            self.session.scroll(steps)

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None


# --------------------------------------------------------------------------- panel


class ScrollPanel(QWidget):
    def __init__(self, can_auto: bool, auto_hint: str):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Raja Capture - Tangkap scroll")
        self.setWindowIcon(icons.app_icon())
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.preview = QLabel()
        self.preview.setFixedSize(120, 160)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#333; border:1px solid #555;")
        self.auto = QCheckBox("Scroll otomatis")
        self.auto.setVisible(can_auto)
        self.auto.setToolTip(auto_hint)
        self.btn_start = QPushButton("Mulai")
        self.btn_start.setDefault(True)
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
        self.setFixedWidth(460)
        self.on_close = None

    def set_preview(self, img: QImage):
        pm = QPixmap.fromImage(img).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)

    def closeEvent(self, e):
        if self.on_close:
            self.on_close()
        super().closeEvent(e)


# --------------------------------------------------------------------------- session


class ScrollCaptureSession(QObject):
    finished = Signal(QImage)
    cancelled = Signal()
    runningChanged = Signal(bool)

    def __init__(self, app, logical_rect: QRect, screen, first_shot):
        super().__init__()
        self.app = app
        self.cfg = app.cfg
        self.backend = app.backend
        self.rect = QRect(logical_rect)
        self.screen = screen
        self.stitcher = Stitcher()
        self.running = False
        self._ended = False
        self.auto = False
        self.scroller = None
        self.direction = 1
        self.flipped = False
        self.same_count = 0
        self.scrolls = 0
        self.steps = max(1, min(5, self.rect.height() // 180))
        self.started_at = 0.0
        self.last_change = 0.0
        self.failed_in_a_row = 0
        self.stop_reason = ""

        self.wayland = is_wayland()
        if self.wayland:
            from ..capture.portal import remote_desktop_available

            can_auto = remote_desktop_available()
            hint = ("Raja Capture men-scroll konten otomatis lewat portal Remote Desktop. "
                    "GNOME akan meminta izin sekali.")
        else:
            can_auto = self.backend.can_auto_scroll
            hint = "Raja Capture mengirim scroll mouse ke area terpilih secara otomatis."
        self.can_auto = can_auto
        self.panel = ScrollPanel(can_auto, hint)
        self.panel.auto.setChecked(can_auto and self.cfg.get("scroll_autoscroll"))
        self.panel.btn_start.clicked.connect(self.start)
        self.panel.btn_done.clicked.connect(self.finish)
        self.panel.btn_cancel.clicked.connect(self.cancel)
        self.panel.on_close = self.cancel
        self.panel.auto.toggled.connect(lambda _v: self._ready_text())
        self._ready_text()
        self._add_frame(first_shot.crop_logical(self.rect))

    # ------------------------------------------------------------ UI helpers
    def _ready_text(self):
        if self.panel.auto.isChecked():
            text = ("Klik <b>Mulai</b>. Halaman akan di-scroll otomatis dan berhenti sendiri di akhir "
                    "halaman.")
            if self.wayland and not self.cfg.get("remote_token"):
                text += ("<br><br><b>Sekali saja:</b> pada dialog GNOME yang muncul, aktifkan "
                         "<b>Izinkan Interaksi Jarak Jauh</b> (Allow Remote Interaction), lalu klik "
                         "<b>Bagikan</b>.")
        else:
            text = ("Klik <b>Mulai</b>, lalu scroll konten di area terpilih <b>pelan-pelan</b> ke bawah. "
                    "Berhenti sendiri beberapa detik setelah Anda berhenti scroll, atau klik "
                    "<b>Selesai</b>.")
            if self.wayland:
                text = ("<b>Geser jendela ini keluar dari area yang dipilih</b> agar tidak ikut "
                        "tertangkap. ") + text
        self.panel.info.setText(text)

    def _panel_overlaps(self) -> bool:
        return QRect(self.panel.pos(), self.panel.size()).intersects(self.rect)

    def show(self):
        self.panel.adjustSize()
        avail = self.screen.availableGeometry() if self.screen else None
        if avail is not None and not self.wayland:
            x = self.rect.right() + 12
            if x + self.panel.width() > avail.right():
                x = self.rect.left() - self.panel.width() - 12
            x = max(avail.left(), x)
            y = min(max(avail.top(), self.rect.top()), avail.bottom() - self.panel.height())
            self.panel.move(x, y)
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _summary(self) -> str:
        return f"{self.stitcher.frames} frame, tinggi {self.stitcher.height} px"

    # ------------------------------------------------------------ start
    def start(self):
        if self.running or self._ended:
            return
        self.auto = self.can_auto and self.panel.auto.isChecked()
        if self.can_auto:  # only remember the choice when the user could actually see it
            self.cfg.set("scroll_autoscroll", self.panel.auto.isChecked())
        self.panel.btn_start.setEnabled(False)
        self.panel.auto.setEnabled(False)
        if self.auto:
            # Prepare while the panel is still visible/focused: GNOME's consent dialog
            # is only shown for the focused app.
            self.panel.info.setText("Menyiapkan scroll otomatis… Pada dialog GNOME, aktifkan "
                                    "<b>Izinkan Interaksi Jarak Jauh</b> lalu klik <b>Bagikan</b>.")
            self.scroller = (PortalScroller(self.cfg, self.rect, self.screen) if self.wayland
                             else QtScroller(self.backend, self.rect))
            self.scroller.prepare(self._begin, self._auto_failed)
        else:
            self._begin()

    def _auto_failed(self, exc):
        self.scroller = None
        self.auto = False
        self.panel.btn_start.setEnabled(True)
        self.panel.auto.setEnabled(True)
        from ..capture.base import CaptureCancelled

        why = "dibatalkan" if isinstance(exc, CaptureCancelled) or not str(exc) else str(exc)
        self.panel.auto.setChecked(True)
        self.panel.info.setText(f"<b>Scroll otomatis belum bisa dipakai:</b> {why}.<br>Klik <b>Mulai</b> "
                                "untuk mencoba lagi (aktifkan <i>Izinkan Interaksi Jarak Jauh</i>), atau "
                                "hapus centang <i>Scroll otomatis</i> untuk scroll manual.")

    def _begin(self):
        if self._ended:
            return
        self.running = True
        self.started_at = self.last_change = time.monotonic()
        self.panel.btn_done.setEnabled(True)
        # Only auto mode hides the panel (it stops by itself); in manual mode the user
        # needs the "Selesai" button, so it stays visible.
        self.hide_while_running = self.auto and (self.wayland or self._panel_overlaps())
        self.runningChanged.emit(True)
        if self.hide_while_running:
            self.panel.hide()
            self.app.notify("Tangkap scroll otomatis berjalan dan berhenti sendiri di akhir halaman. "
                            "Untuk berhenti lebih awal: klik ikon Raja Capture di tray.",
                            "Tangkap scroll")
        else:
            self.panel.info.setText("Menangkap… " + ("halaman di-scroll otomatis." if self.auto
                                                      else "scroll konten pelan-pelan."))
        QTimer.singleShot(300 if self.hide_while_running else 0, self._next)

    # ------------------------------------------------------------ loop
    def _next(self):
        if not self.running or self._ended:
            return
        if self.auto:
            try:
                self.scroller.scroll(self.steps * self.direction)
                self.scrolls += 1
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Scroll otomatis gagal: {exc}", "Tangkap scroll")
                self.finish()
                return
            QTimer.singleShot(SETTLE_MS, self._grab)
        else:
            QTimer.singleShot(max(250, self.cfg.get("scroll_interval_ms")), self._grab)

    def _grab(self):
        if not self.running or self._ended:
            return
        self.backend.grab_async(self._on_shot, self._on_error)

    def _on_error(self, exc):
        if self._ended:
            return
        self.app.notify(f"Gagal mengambil gambar: {exc}", "Tangkap scroll")
        self.finish()

    def _on_shot(self, shot):
        if self._ended or not self.running:
            return
        status = self._add_frame(shot.crop_logical(self.rect))
        now = time.monotonic()
        if status == "added":
            self.same_count = 0
            self.failed_in_a_row = 0
            self.last_change = now
        elif status == "same":
            self.same_count += 1
        else:
            self.failed_in_a_row += 1
        if (self.stitcher.height >= MAX_HEIGHT or self.stitcher.frames >= MAX_FRAMES
                or now - self.started_at >= MAX_SECONDS):
            self.finish()
            return
        if self.auto:
            if status == "same":
                if self.scrolls == 1 and not self.flipped and self.stitcher.frames == 1:
                    self.direction, self.flipped = -self.direction, True  # wrong wheel direction
                elif self.same_count >= 2:
                    if self.stitcher.frames == 1:
                        self.stop_reason = "noscroll"
                    self.finish()  # end of the page (or nothing scrolls)
                    return
            elif status == "nomatch":
                if self.failed_in_a_row >= MAX_FAILED_IN_A_ROW:
                    self.stop_reason = "nomatch"
                    self.finish()
                    return
                if self.steps > 1:
                    self.steps -= 1  # scrolled further than the overlap; take smaller steps
        else:
            idle = now - self.last_change
            moved = self.stitcher.frames > 1
            if (moved and idle >= MANUAL_IDLE_STOP_S) or (not moved and idle >= MANUAL_START_TIMEOUT_S):
                self.finish()
                return
        if not self.hide_while_running:
            warn = "  ⚠ terlalu cepat, scroll lebih pelan" if status == "nomatch" else ""
            self.panel.info.setText(f"Menangkap… {self._summary()}.{warn}")
        self._next()

    def _add_frame(self, img: QImage) -> str:
        status = self.stitcher.add(qimage_to_array(img))
        if status == "added":
            res = self.stitcher.result()
            if res is not None:
                self.panel.set_preview(array_to_qimage(res))
        return status

    # ------------------------------------------------------------ end
    def _end(self):
        was_running = self.running
        self._ended = True
        self.running = False
        if self.scroller is not None:
            self.scroller.close()
            self.scroller = None
        self.panel.on_close = None
        self.panel.close()
        self.panel.deleteLater()
        if was_running:
            self.runningChanged.emit(False)

    def finish(self):
        if self._ended:
            return
        res = self.stitcher.result()
        reason = self.stop_reason
        self._end()
        if reason == "noscroll":
            self.app.notify("Halaman tidak ter-scroll. Pilih area konten yang bisa di-scroll "
                            "(misalnya isi halaman web), atau gunakan scroll manual.", "Tangkap scroll")
        elif reason == "nomatch":
            self.app.notify("Gambar tidak bisa disambung (konten bergerak/berubah). Hasil sejauh ini "
                            "tetap disimpan.", "Tangkap scroll")
        if res is None:
            self.cancelled.emit()
        else:
            self.finished.emit(array_to_qimage(res))

    def cancel(self):
        if self._ended:
            return
        self._end()
        self.cancelled.emit()
