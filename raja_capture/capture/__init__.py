"""Capture backends.

* ``QtBackend``     - Windows, X11, macOS: QScreen.grabWindow + native window list
* ``PortalBackend`` - Wayland: xdg-desktop-portal Screenshot
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from ..util import IS_WINDOWS, is_wayland, is_x11, run_async
from .base import CaptureCancelled, CaptureError, DesktopShot, WindowInfo, virtual_geometry


class CaptureBackend:
    name = "base"
    can_pick_windows = False  # DesktopShot.windows is filled
    has_interactive_window = False  # backend offers its own window picker
    can_auto_scroll = False

    def grab_async(self, on_done, on_error):
        raise NotImplementedError

    def grab_window_interactive_async(self, on_done, on_error):
        raise NotImplementedError

    def scroll(self, x_logical: int, y_logical: int, clicks: int = -3):
        raise NotImplementedError


class QtBackend(CaptureBackend):
    name = "qt"

    def __init__(self):
        self.can_pick_windows = IS_WINDOWS or is_x11()
        self.can_auto_scroll = IS_WINDOWS or is_x11()

    def _list_windows(self, shot_geometry: QRect, scale: float) -> list[WindowInfo]:
        raw = []
        try:
            if IS_WINDOWS:
                from .winenum import list_windows

                raw = list_windows()
            elif is_x11():
                from .x11enum import list_windows

                raw = list_windows()
        except Exception:  # noqa: BLE001 - window picking is best effort
            raw = []
        ox, oy = shot_geometry.x() * scale, shot_geometry.y() * scale
        return [
            WindowInfo(title, QRect(round(x - ox), round(y - oy), w, h)) for title, (x, y, w, h) in raw
        ]

    def grab(self) -> DesktopShot:
        screens = QGuiApplication.screens()
        vg = virtual_geometry()
        scale = max((s.devicePixelRatio() for s in screens), default=1.0)
        img = QImage(round(vg.width() * scale), round(vg.height() * scale), QImage.Format_RGB32)
        img.fill(QColor(0, 0, 0))
        painter = QPainter(img)
        for screen in screens:
            g = screen.geometry()
            pm = screen.grabWindow(0)
            target = QRect(
                round((g.x() - vg.x()) * scale),
                round((g.y() - vg.y()) * scale),
                round(g.width() * scale),
                round(g.height() * scale),
            )
            painter.drawPixmap(target, pm)
        painter.end()
        return DesktopShot(img, vg, self._list_windows(vg, scale))

    def grab_async(self, on_done, on_error):
        def _run():
            try:
                shot = self.grab()
            except Exception as exc:  # noqa: BLE001
                on_error(exc)
                return
            on_done(shot)

        QTimer.singleShot(0, _run)  # QScreen grabbing must happen on the GUI thread

    def scroll(self, x_logical, y_logical, clicks=-3):
        screen = QGuiApplication.screenAt(QRect(x_logical, y_logical, 1, 1).center())
        dpr = screen.devicePixelRatio() if screen else 1.0
        x, y = round(x_logical * dpr), round(y_logical * dpr)
        if IS_WINDOWS:
            from .winenum import scroll_wheel
        else:
            from .x11enum import scroll_wheel
        scroll_wheel(x, y, clicks)


class PortalBackend(CaptureBackend):
    name = "portal"
    has_interactive_window = True

    def grab_async(self, on_done, on_error):
        from .portal import screenshot

        geometry = virtual_geometry()
        run_async(
            screenshot,
            False,
            on_done=lambda img: on_done(DesktopShot(img, geometry, [])),
            on_error=on_error,
        )

    def grab_window_interactive_async(self, on_done, on_error):
        from .portal import screenshot

        run_async(screenshot, True, on_done=on_done, on_error=on_error)


def create_backend() -> CaptureBackend:
    if is_wayland():
        return PortalBackend()
    return QtBackend()


__all__ = [
    "CaptureBackend",
    "CaptureCancelled",
    "CaptureError",
    "DesktopShot",
    "WindowInfo",
    "create_backend",
]
