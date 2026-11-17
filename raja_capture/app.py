"""Raja Capture application controller and entry point."""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

from . import APP_ID, APP_NAME, __version__
from .capture import CaptureCancelled, create_backend
from .capture.base import screen_at_cursor
from .config import ACTION_LABELS, ACTIONS, Config, next_filename
from .hotkeys import HotkeyManager
from .imageio import OPEN_FILTER, save_image
from .ipc import IpcServer, send_to_running
from .recorder import Recorder
from .ui import icons
from .util import is_gnome, is_wayland, restore_child_environment, run_async

CAPTURE_ACTIONS = [a for a, _, _ in ACTIONS]


class RecordingPanel(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.app = app
        self.setWindowTitle("Raja Capture - merekam")
        self.setWindowIcon(icons.app_icon())
        self.label = QLabel("● REC 00:00")
        self.label.setStyleSheet("color:#e53935; font-weight:bold; font-size:15px;")
        stop = QPushButton(icons.icon("stop"), " Stop")
        stop.clicked.connect(app.stop_recording)
        lay = QHBoxLayout(self)
        lay.addWidget(self.label)
        lay.addWidget(stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def start(self, near: QRect | None):
        self.timer.start(500)
        self._tick()
        self.adjustSize()
        if near is not None:
            scr = QGuiApplication.screenAt(near.center())
            if scr:
                avail = scr.availableGeometry()
                x = min(near.right() - self.width(), avail.right() - self.width())
                y = near.bottom() + 8
                if y + self.height() > avail.bottom():
                    y = max(avail.top(), near.top() - self.height() - 8)
                self.move(max(avail.left(), x), y)
        self.show()

    def _tick(self):
        s = int(self.app.recorder.elapsed())
        self.label.setText(f"● REC {s // 60:02d}:{s % 60:02d}")

    def closeEvent(self, e):
        self.timer.stop()
        if self.app.recorder.is_active():
            self.app.stop_recording()
        super().closeEvent(e)


class RajaApp(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.cfg = Config()
        self.backend = create_backend()
        self.editors: set = set()
        self.busy = False
        self._overlay = None
        self._scroll = None
        self._dialogs: list = []
        self._restore_toolbar = False
        self._notified: set = set()
        self._perm_ok = False
        self._last_mode = "region"

        self.recorder = Recorder(self.cfg, self)
        self.recorder.started.connect(self._on_record_started)
        self.recorder.finished.connect(self._on_record_finished)
        self.recorder.failed.connect(self._on_record_failed)
        self.rec_panel: RecordingPanel | None = None
        self._rec_region: QRect | None = None

        from .ui.toolbar import CaptureToolbar

        self.toolbar = CaptureToolbar(self)
        self._build_tray()

        self.ipc = IpcServer(self)
        self.ipc.commandReceived.connect(self.handle_command)

        from .ui.update_dialog import UpdateManager

        self.updates = UpdateManager(self)
        self.updates.start()

        self.hotkeys = HotkeyManager(self.cfg, self)
        self.hotkeys.activated.connect(self.start_capture)
        try:
            self.hotkeys.reload()
        except Exception as exc:  # noqa: BLE001
            self.hotkeys.status = f"Shortcut global gagal diaktifkan: {exc}"

    # ------------------------------------------------------------ tray
    def tray_available(self) -> bool:
        return self.tray is not None

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(icons.app_icon(), self)
        tray.setToolTip(f"{APP_NAME} {__version__}")
        menu = QMenu()
        for action, label, _ in ACTIONS:
            menu.addAction(icons.icon(action if action in ("full", "window", "region", "scroll", "color",
                                                           "ruler", "ocr") else "record"),
                           label, lambda a=action: self.start_capture(a))
        menu.addSeparator()
        self.tray_stop = menu.addAction(icons.icon("stop"), "Hentikan rekaman", self.stop_recording)
        self.tray_stop.setVisible(False)
        self.tray_scroll_stop = menu.addAction(icons.icon("stop"), "Hentikan tangkap scroll",
                                               lambda: self._scroll and self._scroll.finish())
        self.tray_scroll_stop.setVisible(False)
        menu.addAction(icons.icon("open"), "Buka gambar…", self.open_image_dialog)
        menu.addAction("Buka folder hasil", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.cfg.get("output_dir"))))
        menu.addAction("Riwayat upload…", self.show_upload_history)
        menu.addSeparator()
        menu.addAction("Tampilkan toolbar", self.show_toolbar)
        menu.addAction(icons.icon("settings"), "Pengaturan…", self.show_settings)
        menu.addAction("Cek pembaruan…", lambda: self.updates.check(manual=True))
        menu.addAction(f"Tentang Raja Capture {__version__}", self.show_about)
        menu.addAction("Keluar", self.quit)
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray = tray

    def _tray_activated(self, reason):
        if self._scroll is not None and self._scroll.running:
            self._scroll.finish()  # clicking the tray icon stops scrolling capture
            return
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.toolbar.isVisible():
                self.toolbar.hide()
            else:
                self.show_toolbar()

    def notify(self, text: str, title: str = APP_NAME):
        if self.tray is not None:
            self.tray.showMessage(title, text, icons.app_icon(), 4000)
        else:
            print(f"[{title}] {text}")

    def notify_once(self, key: str, text: str):
        if key in self._notified:
            return
        self._notified.add(key)
        self.notify(text)

    def show_toolbar(self):
        self.toolbar.show()
        self.toolbar.raise_()
        self.toolbar.activateWindow()

    # ------------------------------------------------------------ commands
    def handle_command(self, cmd: dict):
        action = cmd.get("action")
        for path in cmd.get("files", []):
            self.open_image_file(path)
        if action in CAPTURE_ACTIONS:
            self.start_capture(action)
        elif action == "show":
            if self._scroll is not None and self._scroll.running:
                self._scroll.finish()  # opening Raja Capture from the app menu stops it
            else:
                self.show_toolbar()
        elif action == "settings":
            self.show_settings()
        elif action == "quit":
            self.quit()

    # ------------------------------------------------------------ capture flow
    def start_capture(self, mode: str):
        if mode in ("record_region", "record_full") and self.recorder.is_active():
            self.stop_recording()  # pressing the record hotkey again stops recording
            return
        if mode == "scroll" and self._scroll is not None:
            self._scroll.finish()  # pressing the scroll hotkey again stops it
            return
        if self.busy or self._scroll is not None:
            return
        if self._needs_screenshot_permission(mode):
            self._ask_permission(lambda: self.start_capture(mode))
            return
        self._last_mode = mode
        self.busy = True
        self._restore_toolbar = self.toolbar.isVisible() and self.cfg.get("hide_toolbar")
        if self._restore_toolbar:
            self.toolbar.hide()
        delay = int(self.cfg.get("delay")) * 1000
        wait = max(delay, 350 if self._restore_toolbar else 60)
        if delay:
            self.notify(f"Menangkap dalam {delay // 1000} detik…")
        QTimer.singleShot(wait, lambda: self._do_capture(mode))

    def _end_capture(self):
        self.busy = False
        self._overlay = None
        if self._restore_toolbar:
            self._restore_toolbar = False
            self.toolbar.show()

    # Wayland/GNOME: an app with a registered id must be granted screenshot access
    # once, and GNOME only shows that dialog while the app has a focused window.
    def _needs_screenshot_permission(self, mode: str) -> bool:
        if self.backend.name != "portal" or self._perm_ok:
            return False
        if mode == "record_full" or (mode == "window" and not self.backend.can_pick_windows):
            return False  # these use interactive portals that ask on their own
        from .capture.portal import screenshot_permission

        self._perm_ok = screenshot_permission() == "yes"
        return not self._perm_ok

    def _ask_permission(self, then):
        from .ui.dialogs import PermissionDialog

        dlg = PermissionDialog()
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        def done(result):
            if result:
                self._perm_ok = True
                self.notify("Izin tangkap layar diberikan.")
                QTimer.singleShot(300, then)

        dlg.finished.connect(done)
        self._keep(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _capture_error(self, exc):
        self._end_capture()
        if isinstance(exc, CaptureCancelled):
            return
        from .capture.portal import PortalAccessDenied

        if isinstance(exc, PortalAccessDenied):
            self._perm_ok = False
            mode = getattr(self, "_last_mode", "region")
            self._ask_permission(lambda: self.start_capture(mode))
            return
        QMessageBox.warning(None, APP_NAME, f"Gagal menangkap layar:\n{exc}")

    def _do_capture(self, mode: str):
        if mode == "window" and not self.backend.can_pick_windows and self.backend.has_interactive_window:
            # Wayland: let the portal's own dialog pick the window.
            def done(img):
                self._end_capture()
                self.deliver(img, "Jendela")

            self.backend.grab_window_interactive_async(done, self._capture_error)
            return
        if mode == "record_full":
            self._end_capture()
            if is_wayland():
                self.recorder.start(None, None, wayland_sources=3)
                self._rec_region = None
            else:
                screen = screen_at_cursor()
                self._rec_region = screen.geometry()
                self.recorder.start(None, screen)
            return
        self.backend.grab_async(lambda shot: self._on_shot(mode, shot), self._capture_error)

    def _on_shot(self, mode: str, shot):
        if mode == "full":
            self._end_capture()
            self.deliver(shot.image, "Layar penuh")
            return
        from .ui.overlay import OverlayController

        overlay_mode = {"window": "window", "color": "color", "ruler": "ruler"}.get(mode, "region")
        hints = {
            "scroll": "Pilih area yang akan di-scroll   •   Esc: batal",
            "record_region": "Pilih area yang akan direkam   •   Esc: batal",
            "ocr": "Pilih area berisi teks   •   Esc: batal",
        }
        ctrl = OverlayController(shot, overlay_mode, hints.get(mode, ""))
        ctrl.cancelled.connect(self._end_capture)
        ctrl.regionSelected.connect(lambda img_rect, logical, screen: self._on_region(
            mode, shot, img_rect, logical, screen))
        ctrl.colorPicked.connect(self._on_color)
        self._overlay = ctrl
        ctrl.start()

    def _on_region(self, mode, shot, img_rect: QRect, logical: QRect, screen):
        if mode == "scroll":
            # keep the toolbar hidden until scrolling capture ends (it would show up in frames)
            self._restore_after_scroll = self._restore_toolbar
            self._restore_toolbar = False
        self._end_capture()
        if mode == "scroll":
            self._start_scroll(shot, logical, screen)
        elif mode == "record_region":
            self._rec_region = logical
            self.recorder.start(logical, screen, wayland_sources=1)
        elif mode == "ocr":
            self._ocr(shot.image.copy(img_rect))
        else:
            self.deliver(shot.image.copy(img_rect), "Jendela" if mode == "window" else "Area")

    def _on_color(self, color):
        self._end_capture()
        from .ui.dialogs import ColorResultDialog

        QGuiApplication.clipboard().setText(color.name().upper())
        dlg = ColorResultDialog(color, on_pick_again=lambda: self.start_capture("color"))
        self._keep(dlg)
        dlg.show()

    def _keep(self, widget):
        self._dialogs.append(widget)
        widget.destroyed.connect(lambda *_: self._dialogs.remove(widget) if widget in self._dialogs else None)

    # ------------------------------------------------------------ scroll
    def _start_scroll(self, shot, logical: QRect, screen):
        from .ui.scroll_capture import ScrollCaptureSession

        sess = ScrollCaptureSession(self, logical, screen, shot)
        sess.finished.connect(self._scroll_finished)
        sess.cancelled.connect(self._scroll_cancelled)
        sess.runningChanged.connect(self._scroll_running)
        self._scroll = sess
        sess.show()

    def _restore_toolbar_after_scroll(self):
        if getattr(self, "_restore_after_scroll", False):
            self._restore_after_scroll = False
            self.toolbar.show()

    def _scroll_finished(self, img: QImage):
        self._scroll = None
        self._restore_toolbar_after_scroll()
        self.deliver(img, "Tangkapan scroll")

    def _scroll_cancelled(self):
        self._scroll = None
        self._restore_toolbar_after_scroll()

    def _scroll_running(self, running: bool):
        if self.tray is not None:
            self.tray_scroll_stop.setVisible(running)

    # ------------------------------------------------------------ OCR
    def _ocr(self, img: QImage):
        from .ocr import find_tesseract, run_ocr
        from .ui.dialogs import TextResultDialog

        exe = find_tesseract(self.cfg.get("tesseract_path"))
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

        def done(text):
            QGuiApplication.restoreOverrideCursor()
            if text:
                QGuiApplication.clipboard().setText(text)
            dlg = TextResultDialog(text, "Hasil OCR (sudah disalin)")
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            self._keep(dlg)
            dlg.show()

        def fail(exc):
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(None, "OCR gagal", str(exc))

        run_async(run_ocr, img, self.cfg.get("ocr_lang"), exe, on_done=done, on_error=fail)

    # ------------------------------------------------------------ recording
    def stop_recording(self):
        self.recorder.stop()

    def _on_record_started(self):
        self.toolbar.set_recording(True)
        if self.tray is not None:
            self.tray_stop.setVisible(True)
            self.tray.setIcon(icons.icon("record"))
        self.rec_panel = RecordingPanel(self)
        self.rec_panel.start(self._rec_region)

    def _record_ui_off(self):
        self.toolbar.set_recording(False)
        if self.tray is not None:
            self.tray_stop.setVisible(False)
            self.tray.setIcon(icons.app_icon())
        if self.rec_panel is not None:
            panel, self.rec_panel = self.rec_panel, None
            panel.timer.stop()
            panel.hide()
            panel.deleteLater()

    def _on_record_finished(self, path: str):
        self._record_ui_off()
        box = QMessageBox(QMessageBox.Information, APP_NAME, f"Rekaman tersimpan:\n{path}")
        open_btn = box.addButton("Putar", QMessageBox.AcceptRole)
        folder_btn = box.addButton("Buka folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif box.clickedButton() is folder_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _on_record_failed(self, msg: str):
        self._record_ui_off()
        if msg:
            QMessageBox.warning(None, APP_NAME, f"Perekaman gagal:\n{msg}")

    # ------------------------------------------------------------ output
    def deliver(self, img: QImage, hint: str = ""):
        action = self.cfg.get("after_capture")
        if action == "editor":
            self.open_editor(img, title_hint=hint)
            return
        msgs = []
        if action in ("save", "save_clipboard"):
            path = next_filename(self.cfg.get("output_dir"), self.cfg.get("filename_pattern"),
                                 self.cfg.get("image_format"))
            if save_image(img, path, self.cfg.get("jpeg_quality")):
                msgs.append(f"Tersimpan: {path}")
            else:
                QMessageBox.warning(None, APP_NAME, f"Gagal menyimpan ke {path}")
        if action in ("clipboard", "save_clipboard"):
            QGuiApplication.clipboard().setImage(img)
            msgs.append("Disalin ke clipboard")
        if msgs:
            self.notify("\n".join(msgs))

    def open_editor(self, img: QImage, path: str | None = None, title_hint: str = ""):
        from .ui.editor import EditorWindow

        ed = EditorWindow(self, img, path, title_hint)
        self.editors.add(ed)
        ed.closed.connect(lambda e: self.editors.discard(e))
        ed.show()
        ed.raise_()
        ed.activateWindow()
        return ed

    def open_image_file(self, path: str):
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(None, APP_NAME, f"Tidak bisa membuka gambar:\n{path}")
            return
        self.open_editor(img, os.path.abspath(path))

    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(None, "Buka gambar", self.cfg.get("output_dir"), OPEN_FILTER)
        if path:
            self.open_image_file(path)

    def show_about(self):
        box = QMessageBox(QMessageBox.NoIcon, f"Tentang {APP_NAME}",
                          f"<h3>{APP_NAME} {__version__}</h3>"
                          "<p>Tangkap, tandai, rekam &amp; bagikan layar.</p>"
                          "<p><a href='https://firexsantos.github.io/raja-capture/'>Website</a> · "
                          "<a href='https://github.com/firexsantos/raja-capture/blob/main/CHANGELOG.md'>"
                          "Catatan perubahan</a> · Lisensi MIT</p>")
        box.setIconPixmap(icons.app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.exec()

    def show_upload_history(self):
        from . import share
        from .ui.dialogs import UploadHistoryDialog

        dlg = UploadHistoryDialog(share.history(self.cfg),
                                  on_clear=lambda: self.cfg.set("upload_history", "[]"))
        self._keep(dlg)
        dlg.show()

    def show_settings(self):
        from .ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self)
        if dlg.exec():
            try:
                self.hotkeys.reload()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(None, APP_NAME, f"Shortcut global gagal diaktifkan:\n{exc}")

    def first_run(self):
        if self.cfg.get("first_run_done"):
            return
        self.cfg.set("first_run_done", True)
        if is_gnome():
            self.notify("Tip: buka Pengaturan → Shortcut → 'Terapkan ke GNOME' untuk mengaktifkan "
                        "shortcut global (Ctrl+Alt+1..9).")

    def quit(self):
        if self.recorder.is_active():
            self.recorder.stop()
        for ed in list(self.editors):
            if not ed.close():
                return
        self.hotkeys.stop()
        if self.tray is not None:
            self.tray.hide()
        self.qapp.quit()


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="raja-capture", description=f"{APP_NAME} {__version__}")
    g = p.add_mutually_exclusive_group()
    for action, label, _ in ACTIONS:
        g.add_argument(f"--{action.replace('_', '-')}", dest="action", action="store_const",
                       const=action, help=label)
    g.add_argument("--show", dest="action", action="store_const", const="show", help="Tampilkan toolbar")
    g.add_argument("--settings", dest="action", action="store_const", const="settings", help="Pengaturan")
    g.add_argument("--quit", dest="action", action="store_const", const="quit", help="Keluar dari instance")
    p.add_argument("--tray", action="store_true", help="Mulai tanpa menampilkan toolbar")
    p.add_argument("files", nargs="*", help="Gambar yang akan dibuka di editor")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    restore_child_environment()
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("RajaCapture")
    QApplication.setApplicationVersion(__version__)
    QGuiApplication.setDesktopFileName(APP_ID)
    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(icons.app_icon())

    files = [os.path.abspath(f) for f in args.files]
    command = {"action": args.action or ("show" if not (args.tray or files) else None), "files": files}
    if send_to_running(command):
        return 0
    if args.action == "quit":
        return 0

    app = RajaApp(qapp)
    for path in files:
        app.open_image_file(path)
    if args.action and args.action not in ("show", "settings"):
        QTimer.singleShot(300, lambda: app.start_capture(args.action))
    elif args.action == "settings":
        QTimer.singleShot(0, app.show_settings)
    elif not args.tray and not files:
        app.show_toolbar()
    if not app.tray_available() and (args.tray or args.action) and not files:
        app.show_toolbar()  # no tray: something must stay visible
    app.first_run()
    return qapp.exec()


__all__ = ["main", "RajaApp", "ACTION_LABELS"]
