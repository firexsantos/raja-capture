"""Platform helpers, background tasks and image conversion utilities."""

from __future__ import annotations

import os
import sys
import traceback

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def is_wayland() -> bool:
    """True when running in a Wayland session (even if Qt itself uses XWayland)."""
    if not IS_LINUX:
        return False
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )


def is_x11() -> bool:
    return IS_LINUX and not is_wayland() and bool(os.environ.get("DISPLAY"))


def is_gnome() -> bool:
    return "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def platform_label() -> str:
    if IS_WINDOWS:
        return "Windows"
    if IS_MAC:
        return "macOS"
    if is_wayland():
        return "Linux (Wayland)"
    return "Linux (X11)"


# --------------------------------------------------------------------------- async


class _TaskSignals(QObject):
    done = Signal(object)
    error = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs, signals):
        super().__init__()
        self.fn, self.args, self.kwargs, self.signals = fn, args, kwargs, signals

    def run(self):  # runs in a worker thread
        try:
            result = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # noqa: BLE001 - forwarded to caller
            exc.__traceback_text__ = traceback.format_exc()
            self.signals.error.emit(exc)
        else:
            self.signals.done.emit(result)


_alive: set = set()


def run_async(fn, *args, on_done=None, on_error=None, **kwargs):
    """Run ``fn`` in the thread pool; callbacks are delivered on the GUI thread."""
    signals = _TaskSignals()
    _alive.add(signals)

    def _done(result):
        _alive.discard(signals)
        if on_done:
            on_done(result)

    def _error(exc):
        _alive.discard(signals)
        if on_error:
            on_error(exc)
        else:
            sys.stderr.write(getattr(exc, "__traceback_text__", repr(exc)))

    signals.done.connect(_done, Qt.QueuedConnection)
    signals.error.connect(_error, Qt.QueuedConnection)
    QThreadPool.globalInstance().start(_Task(fn, args, kwargs, signals))


# --------------------------------------------------------------------------- images


def qimage_to_array(img: QImage) -> np.ndarray:
    """QImage -> (h, w, 3) uint8 RGB array (copy)."""
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)
    return buf[:, : w * 3].reshape(h, w, 3).copy()


def array_to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr[:, :, :3], dtype=np.uint8)
    h, w = arr.shape[:2]
    data = arr.tobytes()
    return QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy()


def quote_arg(arg: str) -> str:
    """Quote an argument for .desktop Exec / g_shell_parse_argv style command lines."""
    if arg and all(c.isalnum() or c in "-_./=:+," for c in arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'
