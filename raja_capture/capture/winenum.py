"""Top-level window enumeration on Windows (z-order, top first)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


def list_windows() -> list[tuple[str, tuple[int, int, int, int]]]:
    """Return [(title, (x, y, w, h))] in physical pixels, topmost first."""
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    result = []

    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if exstyle & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        rect = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                        ctypes.sizeof(rect)) != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w > 1 and h > 1:
            result.append((buf.value, (rect.left, rect.top, w, h)))
        return True

    cb = proc_type(callback)  # keep a reference during the call
    user32.EnumWindows(cb, 0)
    return result


def scroll_wheel(x: int, y: int, clicks: int = -3):
    """Move the cursor to (x, y) physical and send mouse-wheel clicks (negative = down)."""
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    MOUSEEVENTF_WHEEL = 0x0800
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(clicks * 120), 0)
