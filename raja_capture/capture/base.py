"""Common capture data types."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QImage


class CaptureCancelled(Exception):
    """User cancelled the capture (Esc, portal dialog closed, ...)."""


class CaptureError(Exception):
    """Capture failed."""


@dataclass
class WindowInfo:
    title: str
    rect: QRect  # in image pixel coordinates of the DesktopShot


@dataclass
class DesktopShot:
    """A frozen image of the whole virtual desktop.

    ``geometry`` is the virtual desktop in Qt logical coordinates; ``image`` is
    in device pixels, so on HiDPI the image is larger than the geometry.
    """

    image: QImage
    geometry: QRect
    windows: list[WindowInfo] = field(default_factory=list)

    @property
    def scale_x(self) -> float:
        return self.image.width() / max(1, self.geometry.width())

    @property
    def scale_y(self) -> float:
        return self.image.height() / max(1, self.geometry.height())

    def logical_to_image(self, r: QRect) -> QRect:
        sx, sy = self.scale_x, self.scale_y
        x = round((r.x() - self.geometry.x()) * sx)
        y = round((r.y() - self.geometry.y()) * sy)
        out = QRect(x, y, round(r.width() * sx), round(r.height() * sy))
        return out.intersected(self.image.rect())

    def image_to_logical(self, r: QRect) -> QRect:
        sx, sy = self.scale_x, self.scale_y
        return QRect(
            round(r.x() / sx) + self.geometry.x(),
            round(r.y() / sy) + self.geometry.y(),
            round(r.width() / sx),
            round(r.height() / sy),
        )

    def crop_logical(self, r: QRect) -> QImage:
        return self.image.copy(self.logical_to_image(r))


def virtual_geometry() -> QRect:
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    return rect


def screen_at_cursor():
    from PySide6.QtGui import QCursor

    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def physical_rect(logical: QRect, screen) -> QRect:
    """Approximate device-pixel rectangle for ffmpeg-style recorders."""
    dpr = screen.devicePixelRatio() if screen else 1.0
    return QRect(
        round(logical.x() * dpr),
        round(logical.y() * dpr),
        round(logical.width() * dpr),
        round(logical.height() * dpr),
    )


__all__ = [
    "CaptureCancelled",
    "CaptureError",
    "DesktopShot",
    "WindowInfo",
    "virtual_geometry",
    "screen_at_cursor",
    "physical_rect",
    "QPoint",
]
