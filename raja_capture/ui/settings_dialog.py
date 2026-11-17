"""Settings dialog."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import hotkeys, system
from ..config import ACTIONS, AFTER_CAPTURE, IMAGE_FORMATS
from ..util import IS_LINUX, IS_WINDOWS, platform_label
from . import icons


def _dir_row(edit: QLineEdit, parent) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(edit, 1)
    b = QPushButton("…")
    b.setFixedWidth(32)

    def pick():
        d = QFileDialog.getExistingDirectory(parent, "Pilih folder", edit.text())
        if d:
            edit.setText(d)

    b.clicked.connect(pick)
    row.addWidget(b)
    return row


def _file_row(edit: QLineEdit, parent) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(edit, 1)
    b = QPushButton("…")
    b.setFixedWidth(32)

    def pick():
        f, _ = QFileDialog.getOpenFileName(parent, "Pilih program", edit.text())
        if f:
            edit.setText(f)

    b.clicked.connect(pick)
    row.addWidget(b)
    return row


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        cfg = self.cfg = app.cfg
        self.setWindowTitle("Pengaturan Raja Capture")
        self.setWindowIcon(icons.app_icon())
        self.resize(560, 460)
        tabs = QTabWidget()

        # --- General
        g = QWidget()
        f = QFormLayout(g)
        self.out_dir = QLineEdit(cfg.get("output_dir"))
        f.addRow("Folder gambar", _dir_row(self.out_dir, self))
        self.video_dir = QLineEdit(cfg.get("video_dir"))
        f.addRow("Folder video", _dir_row(self.video_dir, self))
        self.pattern = QLineEdit(cfg.get("filename_pattern"))
        self.pattern.setToolTip("Format strftime, mis. Raja_%Y-%m-%d_%H-%M-%S")
        f.addRow("Pola nama file", self.pattern)
        self.fmt = QComboBox()
        self.fmt.addItems(IMAGE_FORMATS)
        self.fmt.setCurrentText(cfg.get("image_format"))
        f.addRow("Format gambar", self.fmt)
        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        self.quality.setValue(cfg.get("jpeg_quality"))
        f.addRow("Kualitas JPG/WEBP", self.quality)
        self.after = QComboBox()
        for key, label in AFTER_CAPTURE:
            self.after.addItem(label, key)
        self.after.setCurrentIndex(max(0, self.after.findData(cfg.get("after_capture"))))
        f.addRow("Setelah menangkap", self.after)
        self.hide_tb = QCheckBox("Sembunyikan toolbar saat menangkap")
        self.hide_tb.setChecked(cfg.get("hide_toolbar"))
        f.addRow("", self.hide_tb)
        self.scroll_ms = QSpinBox()
        self.scroll_ms.setRange(250, 3000)
        self.scroll_ms.setSuffix(" ms")
        self.scroll_ms.setValue(cfg.get("scroll_interval_ms"))
        f.addRow("Interval tangkap scroll", self.scroll_ms)
        f.addRow("Platform", QLabel(f"{platform_label()}  •  backend: {app.backend.name}"))
        tabs.addTab(g, "Umum")

        # --- Hotkeys
        h = QWidget()
        hv = QVBoxLayout(h)
        hf = QFormLayout()
        self.key_edits = {}
        for action, label, _default in ACTIONS:
            e = QKeySequenceEdit(QKeySequence(cfg.hotkey(action)))
            try:
                e.setMaximumSequenceLength(1)
                e.setClearButtonEnabled(True)
            except AttributeError:
                pass
            self.key_edits[action] = e
            hf.addRow(label, e)
        hv.addLayout(hf)
        status = QLabel(app.hotkeys.status)
        status.setWordWrap(True)
        hv.addWidget(status)
        if hotkeys.gnome_available():
            row = QHBoxLayout()
            b1 = QPushButton("Terapkan ke GNOME")
            b1.setToolTip("Menulis shortcut kustom ke Pengaturan Keyboard GNOME (gsettings)")
            b1.clicked.connect(self._gnome_install)
            b2 = QPushButton("Hapus dari GNOME")
            b2.clicked.connect(self._gnome_uninstall)
            row.addWidget(b1)
            row.addWidget(b2)
            row.addStretch(1)
            hv.addLayout(row)
        hv.addStretch(1)
        tabs.addTab(h, "Shortcut")

        # --- Recording & OCR
        r = QWidget()
        rf = QFormLayout(r)
        self.fps = QSpinBox()
        self.fps.setRange(5, 60)
        self.fps.setValue(cfg.get("record_fps"))
        rf.addRow("Frame per detik", self.fps)
        self.rec_cursor = QCheckBox("Rekam kursor mouse")
        self.rec_cursor.setChecked(cfg.get("record_cursor"))
        rf.addRow("", self.rec_cursor)
        from ..recorder import AUDIO_MODES

        self.audio = QComboBox()
        for key, label in AUDIO_MODES:
            self.audio.addItem(label, key)
        self.audio.setCurrentIndex(max(0, self.audio.findData(cfg.get("record_audio"))))
        rf.addRow("Suara", self.audio)
        if IS_WINDOWS:
            self.mic_dev = QComboBox()
            self.sys_dev = QComboBox()
            for combo, key in ((self.mic_dev, "audio_mic_device"), (self.sys_dev, "audio_system_device")):
                combo.setEditable(True)
                combo.setCurrentText(cfg.get(key))
            detect = QPushButton("Deteksi perangkat")
            detect.clicked.connect(self._detect_audio)
            rf.addRow("Mikrofon (DirectShow)", self.mic_dev)
            rf.addRow("Suara sistem (Stereo Mix)", self.sys_dev)
            rf.addRow("", detect)
        self.ffmpeg = QLineEdit(cfg.get("ffmpeg_path"))
        self.ffmpeg.setPlaceholderText("otomatis dari PATH")
        rf.addRow("ffmpeg (Windows/X11)", _file_row(self.ffmpeg, self))
        reset = QPushButton("Lupakan pilihan layar portal")
        reset.setToolTip("Wayland: tampilkan lagi dialog pilih layar saat merekam")
        reset.clicked.connect(lambda: (cfg.set("screencast_token", ""), reset.setEnabled(False)))
        rf.addRow("", reset)
        self.ocr_lang = QLineEdit(cfg.get("ocr_lang"))
        self.ocr_lang.setToolTip("Kode bahasa Tesseract, mis. eng, ind, atau eng+ind")
        rf.addRow("Bahasa OCR", self.ocr_lang)
        self.tess = QLineEdit(cfg.get("tesseract_path"))
        self.tess.setPlaceholderText("otomatis dari PATH")
        rf.addRow("Tesseract", _file_row(self.tess, self))
        langs_label = QLabel()
        from ..ocr import available_languages, find_tesseract

        exe = find_tesseract(cfg.get("tesseract_path"))
        langs_label.setText(f"Bahasa terpasang: {', '.join(available_languages(exe)) or '-'}" if exe
                            else "Tesseract belum terpasang.")
        langs_label.setWordWrap(True)
        rf.addRow("", langs_label)
        tabs.addTab(r, "Rekam & OCR")

        # --- Sharing
        u = QWidget()
        uf = QFormLayout(u)
        self.imgur = QLineEdit(cfg.get("imgur_client_id"))
        self.imgur.setPlaceholderText("Client ID dari api.imgur.com/oauth2/addclient")
        uf.addRow("Imgur Client ID", self.imgur)
        info = QLabel('<a href="https://api.imgur.com/oauth2/addclient">Daftar aplikasi Imgur</a> '
                      '(gratis, pilih "Anonymous usage without user authorization").')
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        uf.addRow("", info)
        uf.addRow(QLabel("<b>Server kustom</b> (POST multipart, mirip ShareX)"))
        self.up_url = QLineEdit(cfg.get("custom_upload_url"))
        self.up_url.setPlaceholderText("https://contoh.com/upload")
        uf.addRow("URL", self.up_url)
        self.up_field = QLineEdit(cfg.get("custom_upload_field"))
        uf.addRow("Nama field file", self.up_field)
        self.up_headers = QLineEdit(cfg.get("custom_upload_headers"))
        self.up_headers.setPlaceholderText('{"Authorization": "Bearer TOKEN"}')
        uf.addRow("Header (JSON)", self.up_headers)
        self.up_resp = QLineEdit(cfg.get("custom_upload_response"))
        self.up_resp.setPlaceholderText("mis. data.url  (kosong = isi jawaban apa adanya)")
        uf.addRow("Lokasi link di JSON", self.up_resp)
        tabs.addTab(u, "Kirim")

        # --- System
        s = QWidget()
        sv = QVBoxLayout(s)
        self.autostart = QCheckBox("Jalankan Raja Capture saat login")
        try:
            self.autostart.setChecked(system.autostart_enabled())
        except Exception:  # noqa: BLE001
            self.autostart.setEnabled(False)
        self._autostart_initial = self.autostart.isChecked()
        sv.addWidget(self.autostart)
        if IS_LINUX:
            b = QPushButton("Pasang ke menu aplikasi (.desktop)")
            b.clicked.connect(self._install_desktop)
            sv.addWidget(b)
        cmd = QLineEdit(" ".join(system.launcher_argv()) + " --region")
        cmd.setReadOnly(True)
        sv.addWidget(QLabel("Perintah CLI (bisa dipakai untuk shortcut manual):"))
        sv.addWidget(cmd)
        sv.addStretch(1)
        tabs.addTab(s, "Sistem")
        if not (IS_LINUX or IS_WINDOWS):
            self.autostart.setEnabled(False)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    def _detect_audio(self):
        import shutil

        from ..recorder import list_dshow_audio_devices

        exe = self.ffmpeg.text().strip() or shutil.which("ffmpeg")
        devices = list_dshow_audio_devices(exe) if exe else []
        if not devices:
            QMessageBox.information(self, "Audio", "Tidak ada perangkat audio terdeteksi (perlu ffmpeg). "
                                    "Untuk suara sistem aktifkan 'Stereo Mix' di pengaturan Sound Windows.")
            return
        for combo in (self.mic_dev, self.sys_dev):
            current = combo.currentText()
            combo.clear()
            combo.addItems(devices)
            combo.setCurrentText(current)
        for d in devices:
            if "stereo mix" in d.lower() or "loopback" in d.lower():
                self.sys_dev.setCurrentText(d)

    def _save_hotkeys(self):
        for action, e in self.key_edits.items():
            self.cfg.set_hotkey(action, e.keySequence().toString(QKeySequence.PortableText))

    def _gnome_install(self):
        self._save_hotkeys()
        labels = {a: label for a, label, _ in ACTIONS}
        try:
            n = hotkeys.gnome_install(self.cfg.hotkeys(), labels, system.launcher_argv())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "GNOME", f"Gagal memasang shortcut:\n{exc}")
            return
        QMessageBox.information(self, "GNOME", f"{n} shortcut dipasang ke GNOME.\n"
                                "Cek di Pengaturan → Keyboard → Shortcut Kustom.")

    def _gnome_uninstall(self):
        try:
            n = hotkeys.gnome_uninstall()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "GNOME", f"Gagal menghapus shortcut:\n{exc}")
            return
        QMessageBox.information(self, "GNOME", f"{n} shortcut Raja Capture dihapus dari GNOME.")

    def _install_desktop(self):
        try:
            path = system.install_desktop_entry()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Menu aplikasi", str(exc))
            return
        QMessageBox.information(self, "Menu aplikasi", f"Dipasang: {path}")

    def accept(self):
        c = self.cfg
        c.set("output_dir", self.out_dir.text().strip())
        c.set("video_dir", self.video_dir.text().strip())
        c.set("filename_pattern", self.pattern.text().strip() or "Raja_%Y-%m-%d_%H-%M-%S")
        c.set("image_format", self.fmt.currentText())
        c.set("jpeg_quality", self.quality.value())
        c.set("after_capture", self.after.currentData())
        c.set("hide_toolbar", self.hide_tb.isChecked())
        c.set("scroll_interval_ms", self.scroll_ms.value())
        c.set("record_fps", self.fps.value())
        c.set("record_cursor", self.rec_cursor.isChecked())
        c.set("record_audio", self.audio.currentData())
        if IS_WINDOWS:
            c.set("audio_mic_device", self.mic_dev.currentText().strip())
            c.set("audio_system_device", self.sys_dev.currentText().strip())
        c.set("ffmpeg_path", self.ffmpeg.text().strip())
        c.set("ocr_lang", self.ocr_lang.text().strip() or "eng")
        c.set("tesseract_path", self.tess.text().strip())
        c.set("imgur_client_id", self.imgur.text().strip())
        c.set("custom_upload_url", self.up_url.text().strip())
        c.set("custom_upload_field", self.up_field.text().strip() or "file")
        c.set("custom_upload_headers", self.up_headers.text().strip())
        c.set("custom_upload_response", self.up_resp.text().strip())
        self._save_hotkeys()
        if self.autostart.isEnabled() and self.autostart.isChecked() != self._autostart_initial:
            try:
                system.set_autostart(self.autostart.isChecked())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Autostart", str(exc))
        c.sync()
        super().accept()
