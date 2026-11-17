"""Screen recording.

* Wayland : ScreenCast portal -> PipeWire fd -> gst-launch-1.0 (pipewiresrc ! x264enc ! mp4mux)
* Windows : ffmpeg -f gdigrab
* X11     : ffmpeg -f x11grab
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time

from PySide6.QtCore import QObject, QRect, QTimer, Signal

from .capture.base import physical_rect
from .config import next_filename
from .util import IS_MAC, IS_WINDOWS, is_wayland, run_async


class RecorderError(Exception):
    pass


def _even(v: int) -> int:
    return max(2, v - (v % 2))


class Recorder(QObject):
    started = Signal()
    finished = Signal(str)  # output path
    failed = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.session = None
        self.path: str | None = None
        self.log_path: str | None = None
        self.started_at = 0.0
        self._stopping = False
        self._starting = False
        self._watch = QTimer(self)
        self._watch.setInterval(700)
        self._watch.timeout.connect(self._check_alive)

    # ------------------------------------------------------------ state
    def is_active(self) -> bool:
        return self.proc is not None or self._starting

    def elapsed(self) -> float:
        return time.time() - self.started_at if self.proc else 0.0

    def _new_paths(self):
        self.path = next_filename(self.cfg.get("video_dir"), self.cfg.get("filename_pattern"), "mp4")
        fd, self.log_path = tempfile.mkstemp(prefix="raja-rec-", suffix=".log")
        os.close(fd)

    # ------------------------------------------------------------ start
    def start(self, logical_rect: QRect | None, screen, wayland_sources: int = 1):
        """Record ``logical_rect`` on ``screen`` (None = whole screen).

        On Wayland, ``wayland_sources`` is the portal source type mask
        (1 = monitor, 2 = window, 3 = both).
        """
        if self.is_active():
            return
        self._new_paths()
        fps = max(5, min(60, self.cfg.get("record_fps")))
        if is_wayland():
            self._starting = True
            run_async(self._wayland_prepare, logical_rect, screen, wayland_sources, fps,
                      on_done=self._on_proc_started, on_error=self._on_start_error)
        else:
            try:
                self._on_proc_started((None, self._start_ffmpeg(logical_rect, screen, fps), None))
            except Exception as exc:  # noqa: BLE001
                self._on_start_error(exc)

    def _wayland_prepare(self, logical_rect, screen, sources, fps):
        from .capture.portal import ScreenCastSession

        gst = shutil.which("gst-launch-1.0")
        if not gst:
            raise RecorderError("gst-launch-1.0 tidak ditemukan. Pasang paket gstreamer1.0-tools, "
                                "gstreamer1.0-pipewire dan gstreamer1.0-plugins-ugly (x264).")
        session = ScreenCastSession()
        try:
            persist = sources == 1
            token = self.cfg.get("screencast_token") if persist else None
            node, size = session.start(sources, cursor=self.cfg.get("record_cursor"),
                                       restore_token=token or None, persist=persist)
            crop = None
            if size:
                sw, sh = size
                left = top = 0
                cw, ch = sw, sh
                if logical_rect is not None and screen is not None and sources == 1:
                    g = screen.geometry()
                    f = sw / max(1, g.width())
                    # Only crop when the stream really is this monitor.
                    if abs(sh / max(1, g.height()) - f) < 0.02:
                        left = max(0, round((logical_rect.x() - g.x()) * f))
                        top = max(0, round((logical_rect.y() - g.y()) * f))
                        cw = min(sw - left, round(logical_rect.width() * f))
                        ch = min(sh - top, round(logical_rect.height() * f))
                cw, ch = _even(cw), _even(ch)
                crop = (left, top, sw - left - cw, sh - top - ch)
            cmd = [gst, "-e", "pipewiresrc", f"fd={session.fd}", f"path={node}", "do-timestamp=true",
                   "keepalive-time=1000", "always-copy=true", "!", "videoconvert", "!", "videorate", "!",
                   f"video/x-raw,framerate={fps}/1"]
            if crop and any(crop):
                l, t, r, b = crop
                cmd += ["!", "videocrop", f"left={l}", f"top={t}", f"right={r}", f"bottom={b}"]
            cmd += ["!", "videoconvert", "!", "video/x-raw,format=I420", "!", "x264enc",
                    "speed-preset=veryfast", "tune=zerolatency", "bitrate=6000", "key-int-max=60", "!",
                    "h264parse", "!", "mp4mux", "!", "filesink", f"location={self.path}"]
            with open(self.log_path, "w") as log:
                proc = subprocess.Popen(cmd, pass_fds=(session.fd,), stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT)
            return session, proc, session.restore_token
        except BaseException:
            session.close()
            raise

    def _ffmpeg(self) -> str:
        exe = self.cfg.get("ffmpeg_path") or shutil.which("ffmpeg")
        if not exe or not (os.path.exists(exe) or shutil.which(exe)):
            raise RecorderError("ffmpeg tidak ditemukan. Pasang ffmpeg dan pastikan ada di PATH, "
                                "atau atur lokasinya di Pengaturan.")
        return exe

    def _start_ffmpeg(self, logical_rect, screen, fps):
        from PySide6.QtGui import QGuiApplication

        exe = self._ffmpeg()
        screen = screen or QGuiApplication.primaryScreen()
        rect = physical_rect(logical_rect or screen.geometry(), screen)
        x, y, w, h = rect.x(), rect.y(), _even(rect.width()), _even(rect.height())
        cursor = "1" if self.cfg.get("record_cursor") else "0"
        if IS_WINDOWS:
            src = ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", cursor, "-offset_x", str(x),
                   "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop"]
        elif IS_MAC:
            raise RecorderError("Perekaman layar di macOS belum didukung pada versi ini.")
        else:
            display = os.environ.get("DISPLAY", ":0")
            src = ["-f", "x11grab", "-framerate", str(fps), "-draw_mouse", cursor, "-video_size",
                   f"{w}x{h}", "-i", f"{display}+{x},{y}"]
        cmd = [exe, "-y", "-hide_banner", "-loglevel", "warning", *src, "-c:v", "libx264", "-preset",
               "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", self.path]
        flags = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW
        with open(self.log_path, "w") as log:
            return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=flags)

    def _on_proc_started(self, result):
        session, proc, token = result
        self._starting = False
        self.session, self.proc = session, proc
        if token:
            self.cfg.set("screencast_token", token)
        self.started_at = time.time()
        self._stopping = False
        self._watch.start()
        self.started.emit()

    def _on_start_error(self, exc):
        self._starting = False
        self.proc = None
        from .capture.base import CaptureCancelled

        if isinstance(exc, CaptureCancelled):
            self.failed.emit("")  # silent cancel
            return
        if self.cfg.get("screencast_token") and is_wayland():
            self.cfg.set("screencast_token", "")  # stale token? try fresh next time
        self.failed.emit(str(exc) or exc.__class__.__name__)

    # ------------------------------------------------------------ stop
    def stop(self):
        if self.proc is None or self._stopping:
            return
        self._stopping = True
        self._watch.stop()
        proc, session = self.proc, self.session
        run_async(self._stop_blocking, proc, session, on_done=self._on_stopped,
                  on_error=lambda e: self._finish_error(str(e)))

    @staticmethod
    def _stop_blocking(proc, session):
        try:
            if IS_WINDOWS or session is None:
                try:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
                except (OSError, AttributeError, ValueError):
                    proc.terminate()
            else:
                proc.send_signal(signal.SIGINT)  # gst-launch -e -> EOS -> mp4 finalized
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        finally:
            if session is not None:
                session.close()
        return proc.returncode

    def _on_stopped(self, _code):
        path = self.path
        self.proc = None
        self.session = None
        self._stopping = False
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            self.finished.emit(path)
        else:
            self._finish_error("File video tidak terbentuk.\n" + self._log_tail())

    def _finish_error(self, msg: str):
        self.proc = None
        self.session = None
        self._stopping = False
        self.failed.emit(msg)

    def _check_alive(self):
        if self.proc is not None and not self._stopping and self.proc.poll() is not None:
            self._watch.stop()
            session, self.session = self.session, None
            if session is not None:
                session.close()
            self.proc = None
            path = self.path
            if path and os.path.exists(path) and os.path.getsize(path) > 1024:
                self.finished.emit(path)  # e.g. the user stopped sharing via GNOME's indicator
            else:
                self.failed.emit("Perekaman berhenti tiba-tiba.\n" + self._log_tail())

    def _log_tail(self) -> str:
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-12:])
        except (OSError, TypeError):
            return ""
