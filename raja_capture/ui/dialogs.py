"""Small dialogs: resize image, OCR text result, color picker result."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class ResizeDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ubah ukuran gambar")
        self._ratio = width / max(1, height)
        self._lock = False
        form = QFormLayout()
        self.w = QSpinBox()
        self.w.setRange(1, 20000)
        self.w.setValue(width)
        self.h = QSpinBox()
        self.h.setRange(1, 20000)
        self.h.setValue(height)
        self.pct = QSpinBox()
        self.pct.setRange(1, 1000)
        self.pct.setSuffix(" %")
        self.pct.setValue(100)
        self.keep = QCheckBox("Pertahankan rasio")
        self.keep.setChecked(True)
        form.addRow("Lebar (px)", self.w)
        form.addRow("Tinggi (px)", self.h)
        form.addRow("Persentase", self.pct)
        form.addRow("", self.keep)
        self._orig = (width, height)
        self.w.valueChanged.connect(self._w_changed)
        self.h.valueChanged.connect(self._h_changed)
        self.pct.valueChanged.connect(self._pct_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _w_changed(self, v):
        if self._lock or not self.keep.isChecked():
            return
        self._lock = True
        self.h.setValue(max(1, round(v / self._ratio)))
        self._lock = False

    def _h_changed(self, v):
        if self._lock or not self.keep.isChecked():
            return
        self._lock = True
        self.w.setValue(max(1, round(v * self._ratio)))
        self._lock = False

    def _pct_changed(self, v):
        self._lock = True
        self.w.setValue(max(1, round(self._orig[0] * v / 100)))
        self.h.setValue(max(1, round(self._orig[1] * v / 100)))
        self._lock = False

    def size_value(self) -> tuple[int, int]:
        return self.w.value(), self.h.value()


class TextResultDialog(QDialog):
    def __init__(self, text: str, title="Hasil OCR", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 420)
        self.edit = QPlainTextEdit(text)
        copy_btn = QPushButton("Salin semua")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(copy_btn)
        row.addWidget(close_btn)
        lay = QVBoxLayout(self)
        if not text.strip():
            lay.addWidget(QLabel("Tidak ada teks yang terdeteksi."))
        lay.addWidget(self.edit)
        lay.addLayout(row)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.edit.toPlainText())


class ColorResultDialog(QDialog):
    def __init__(self, color: QColor, on_pick_again=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pemilih warna")
        self.setAttribute(Qt.WA_DeleteOnClose)
        swatch = QFrame()
        swatch.setFixedSize(96, 96)
        swatch.setStyleSheet(f"background:{color.name()}; border:1px solid #888; border-radius:6px;")
        h, s, l, _ = color.getHsl()
        values = [
            ("HEX", color.name().upper()),
            ("RGB", f"rgb({color.red()}, {color.green()}, {color.blue()})"),
            ("HSL", f"hsl({max(h, 0)}, {round(s / 2.55)}%, {round(l / 2.55)}%)"),
            ("Delphi/BGR", f"${color.blue():02X}{color.green():02X}{color.red():02X}"),
        ]
        grid = QGridLayout()
        for row, (name, val) in enumerate(values):
            grid.addWidget(QLabel(name), row, 0)
            field = QLineEdit(val)
            field.setReadOnly(True)
            grid.addWidget(field, row, 1)
            btn = QPushButton("Salin")
            btn.clicked.connect(lambda _=False, v=val: QGuiApplication.clipboard().setText(v))
            grid.addWidget(btn, row, 2)
        top = QHBoxLayout()
        top.addWidget(swatch)
        top.addLayout(grid, 1)
        again = QPushButton("Ambil warna lagi")
        close = QPushButton("Tutup")
        close.clicked.connect(self.close)
        if on_pick_again:
            again.clicked.connect(lambda: (self.close(), on_pick_again()))
        else:
            again.hide()
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(again)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(QLabel("HEX sudah disalin ke clipboard."))
        lay.addLayout(row)


class UploadResultDialog(QDialog):
    def __init__(self, result: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        self.setWindowTitle(f"Upload berhasil - {result.get('service', '')}")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(520, 0)
        url = result["url"]
        QGuiApplication.clipboard().setText(url)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Link sudah disalin ke clipboard:"))
        grid = QGridLayout()
        rows = [("Link", url)]
        if result.get("delete_url"):
            rows.append(("Link hapus", result["delete_url"]))
        for r, (name, val) in enumerate(rows):
            grid.addWidget(QLabel(name), r, 0)
            field = QLineEdit(val)
            field.setReadOnly(True)
            grid.addWidget(field, r, 1)
            copy = QPushButton("Salin")
            copy.clicked.connect(lambda _=False, v=val: QGuiApplication.clipboard().setText(v))
            grid.addWidget(copy, r, 2)
            open_btn = QPushButton("Buka")
            open_btn.clicked.connect(lambda _=False, v=val: QDesktopServices.openUrl(QUrl(v)))
            grid.addWidget(open_btn, r, 3)
        lay.addLayout(grid)
        if result.get("delete_url"):
            note = QLabel("Simpan link hapus jika ingin menghapus gambar ini nanti "
                          "(juga tersimpan di Riwayat upload).")
            note.setWordWrap(True)
            lay.addWidget(note)
        close = QPushButton("Tutup")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)


class UploadHistoryDialog(QDialog):
    def __init__(self, entries: list[dict], on_clear=None, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

        self.setWindowTitle("Riwayat upload")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(720, 380)
        table = QTableWidget(len(entries), 4)
        table.setHorizontalHeaderLabels(["Waktu", "Layanan", "Link", "Link hapus"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, e in enumerate(entries):
            for c, key in enumerate(("time", "service", "url", "delete_url")):
                table.setItem(r, c, QTableWidgetItem(str(e.get(key, ""))))
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        table.cellDoubleClicked.connect(
            lambda r, c: QDesktopServices.openUrl(QUrl(table.item(r, c).text())) if c >= 2 else None)
        self.table = table
        copy = QPushButton("Salin link")
        copy.clicked.connect(self._copy)
        clear = QPushButton("Hapus riwayat")
        clear.clicked.connect(lambda: (on_clear and on_clear(), table.setRowCount(0)))
        close = QPushButton("Tutup")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(clear)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Klik dua kali pada link untuk membukanya di browser."))
        lay.addWidget(table)
        lay.addLayout(row)

    def _copy(self):
        r = self.table.currentRow()
        if r >= 0:
            QGuiApplication.clipboard().setText(self.table.item(r, 2).text())


class PermissionDialog(QDialog):
    """Asks GNOME for screenshot permission while one of our windows has focus.

    GNOME only shows its access dialog for the focused app, so this request must
    happen from a visible, focused Raja Capture window (not after hiding the toolbar).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from ..capture import portal
        from . import icons

        self.portal = portal
        self.setWindowTitle("Izin tangkap layar")
        self.setWindowIcon(icons.app_icon())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(460)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.btn_allow = QPushButton("Izinkan sekarang")
        self.btn_allow.setDefault(True)
        self.btn_reset = QPushButton("Reset izin && minta lagi")
        self.btn_cancel = QPushButton("Batal")
        self.btn_allow.clicked.connect(self._request)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.btn_reset)
        row.addStretch(1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_allow)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self):
        state = self.portal.screenshot_permission()
        if state == "no":
            self.info.setText("<b>Izin tangkap layar sebelumnya ditolak.</b><br>Klik <i>Reset izin &amp; "
                              "minta lagi</i>, lalu pilih <b>Izinkan</b> pada dialog GNOME.")
            self.btn_reset.show()
            self.btn_allow.setEnabled(False)
        else:
            self.info.setText("<b>Raja Capture perlu izin untuk menangkap layar.</b><br>Ini hanya sekali. "
                              "Klik <i>Izinkan sekarang</i>, lalu pilih <b>Izinkan</b> (Allow) pada dialog "
                              "GNOME yang muncul.")
            self.btn_reset.hide()
            self.btn_allow.setEnabled(True)

    def _reset(self):
        try:
            self.portal.reset_screenshot_permission()
        except Exception as exc:  # noqa: BLE001
            self.info.setText(f"Gagal mereset izin: {exc}")
            return
        self._refresh()
        self._request()

    def _request(self):
        from ..util import run_async

        self.btn_allow.setEnabled(False)
        self.btn_reset.setEnabled(False)
        self.info.setText("Menunggu persetujuan… pilih <b>Izinkan</b> pada dialog GNOME.")
        self.raise_()
        self.activateWindow()
        run_async(self.portal.screenshot, False, on_done=lambda _img: self.accept(),
                  on_error=self._failed)

    def _failed(self, exc):
        self.btn_reset.setEnabled(True)
        self._refresh()
        if self.portal.screenshot_permission() != "no":
            self.info.setText(f"<b>Izin belum diberikan.</b><br>{exc}<br>Pastikan jendela ini aktif "
                              "(klik sekali di jendela ini), lalu coba lagi.")
