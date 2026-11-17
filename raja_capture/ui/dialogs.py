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
