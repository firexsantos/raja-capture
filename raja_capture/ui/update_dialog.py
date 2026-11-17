"""Update notification popup, download progress and the periodic update checker."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .. import __version__, updater
from ..util import run_async
from . import icons

CHECK_EVERY_MS = 6 * 3600 * 1000
MIN_AUTO_INTERVAL_S = 12 * 3600
FIRST_CHECK_DELAY_MS = 15_000


class UpdateDialog(QDialog):
    UPGRADE, LATER, SKIP = 1, 2, 3

    def __init__(self, info: dict, kind: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pembaruan Raja Capture tersedia")
        self.setWindowIcon(icons.app_icon())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(560, 460)
        self.choice = self.LATER
        title = QLabel(f"<h2 style='margin:0'>Raja Capture {info['version']} sudah tersedia</h2>"
                       f"<p style='margin:4px 0 0'>Versi Anda saat ini: {__version__}</p>")
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(56, 56))
        head = QHBoxLayout()
        head.addWidget(logo)
        head.addWidget(title, 1)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.get("notes") or "_Tidak ada catatan rilis._")
        self.auto = updater.can_self_update(kind)
        hint = QLabel("Raja Capture akan mengunduh, memasang, lalu membuka ulang dirinya otomatis."
                      if self.auto else
                      "Instalasi ini tidak bisa diperbarui otomatis. Unduh versi baru dari halaman rilis.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text);")
        b_skip = QPushButton("Lewati versi ini")
        b_later = QPushButton("Nanti")
        b_go = QPushButton("Upgrade sekarang" if self.auto else "Buka halaman unduh")
        b_go.setDefault(True)
        b_skip.clicked.connect(lambda: self._done(self.SKIP))
        b_later.clicked.connect(lambda: self._done(self.LATER))
        b_go.clicked.connect(lambda: self._done(self.UPGRADE))
        row = QHBoxLayout()
        row.addWidget(b_skip)
        row.addStretch(1)
        row.addWidget(b_later)
        row.addWidget(b_go)
        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addWidget(QLabel("<b>Yang baru:</b>"))
        lay.addWidget(notes, 1)
        lay.addWidget(hint)
        lay.addLayout(row)

    def _done(self, choice: int):
        self.choice = choice
        self.accept()


class _DownloadThread(QThread):
    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, asset: dict, dest_dir: str | None):
        super().__init__()
        self.asset, self.dest_dir = asset, dest_dir
        self.cancel_requested = False

    def run(self):
        try:
            path = updater.download(self.asset, self.dest_dir,
                                    progress=lambda d, t: self.progress.emit(d, t),
                                    cancelled=lambda: self.cancel_requested)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(path)


class UpdateManager(QObject):
    """Checks GitHub Releases periodically and drives the upgrade."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg
        self.kind = updater.install_kind()
        self._busy = False
        self._dialog = None
        self._thread = None
        self.latest: dict | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_EVERY_MS)
        self.timer.timeout.connect(lambda: self.check(manual=False))

    def start(self):
        if self.cfg.get("check_updates"):
            QTimer.singleShot(FIRST_CHECK_DELAY_MS, lambda: self.check(manual=False))
            self.timer.start()

    # ------------------------------------------------------------ checking
    def check(self, manual: bool = False):
        if self._busy or self._dialog is not None:
            return
        if not manual:
            if not self.cfg.get("check_updates"):
                return
            if time.time() - self.cfg.get("last_update_check") < MIN_AUTO_INTERVAL_S:
                return
        self._busy = True
        run_async(updater.fetch_latest, on_done=lambda info: self._on_info(info, manual),
                  on_error=lambda exc: self._on_error(exc, manual))

    def _on_error(self, exc, manual):
        self._busy = False
        if manual:
            QMessageBox.warning(None, "Cek pembaruan", f"Gagal memeriksa pembaruan:\n{exc}")

    def _on_info(self, info: dict, manual: bool):
        self._busy = False
        self.cfg.set("last_update_check", int(time.time()))
        self.latest = info
        if not updater.is_newer(info["version"]):
            if manual:
                QMessageBox.information(None, "Cek pembaruan",
                                        f"Anda sudah memakai versi terbaru ({__version__}).")
            return
        if not manual and self.cfg.get("skipped_version") == info["version"]:
            return
        self.app.notify(f"Raja Capture {info['version']} tersedia. Klik untuk melihat yang baru.",
                        "Pembaruan tersedia")
        self.show_dialog(info)

    # ------------------------------------------------------------ dialog
    def show_dialog(self, info: dict | None = None):
        info = info or self.latest
        if info is None or self._dialog is not None:
            return
        dlg = UpdateDialog(info, self.kind)
        self._dialog = dlg
        dlg.finished.connect(lambda _r: self._on_choice(dlg, info))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_choice(self, dlg: UpdateDialog, info: dict):
        self._dialog = None
        dlg.deleteLater()
        if dlg.choice == UpdateDialog.SKIP:
            self.cfg.set("skipped_version", info["version"])
        elif dlg.choice == UpdateDialog.UPGRADE:
            if updater.can_self_update(self.kind):
                self.upgrade(info)
            else:
                QDesktopServices.openUrl(QUrl(info.get("url") or updater.RELEASES_PAGE))

    # ------------------------------------------------------------ upgrade
    def upgrade(self, info: dict):
        asset = updater.pick_asset(self.kind, info["assets"])
        if asset is None:
            QMessageBox.warning(None, "Upgrade", "Paket untuk instalasi ini tidak ada di rilis terbaru.")
            QDesktopServices.openUrl(QUrl(info.get("url") or updater.RELEASES_PAGE))
            return
        try:
            dest = updater.appimage_download_dir() if self.kind == "appimage" else None
        except updater.UpdateError as exc:
            QMessageBox.warning(None, "Upgrade", str(exc))
            return
        progress = QProgressDialog(f"Mengunduh Raja Capture {info['version']}…", "Batal", 0, 100)
        progress.setWindowTitle("Upgrade Raja Capture")
        progress.setWindowIcon(icons.app_icon())
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        thread = _DownloadThread(asset, dest)
        self._thread = thread

        def on_progress(done, total):
            if total:
                progress.setValue(int(done * 100 / total))
                progress.setLabelText(f"Mengunduh Raja Capture {info['version']}…  "
                                      f"{done / 1048576:.1f} / {total / 1048576:.1f} MB")

        def on_failed(msg):
            progress.close()
            self._thread = None
            if "dibatalkan" not in msg:
                QMessageBox.warning(None, "Upgrade gagal", msg)

        def on_ok(path):
            progress.setLabelText("Memasang pembaruan…")
            progress.setCancelButton(None)
            progress.setRange(0, 0)
            self._thread = None
            run_async(updater.apply_update, self.kind, path,
                      on_done=lambda cmd: self._installed(progress, cmd),
                      on_error=lambda exc: on_failed(str(exc)))

        thread.progress.connect(on_progress)
        thread.failed.connect(on_failed)
        thread.finished_ok.connect(on_ok)
        progress.canceled.connect(lambda: setattr(thread, "cancel_requested", True))
        thread.start()

    def _installed(self, progress, relaunch_cmd):
        progress.close()
        if relaunch_cmd:
            updater.relaunch_after_exit(relaunch_cmd)
        self.app.quit()
