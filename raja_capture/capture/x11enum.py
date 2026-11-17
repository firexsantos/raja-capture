"""Window enumeration and synthetic scrolling on X11 (optional python-xlib)."""

from __future__ import annotations

try:
    from Xlib import X, display
    from Xlib.ext import xtest

    HAVE_XLIB = True
except ImportError:
    HAVE_XLIB = False


def list_windows() -> list[tuple[str, tuple[int, int, int, int]]]:
    if not HAVE_XLIB:
        return []
    d = display.Display()
    try:
        root = d.screen().root
        stacking = root.get_full_property(d.intern_atom("_NET_CLIENT_LIST_STACKING"), X.AnyPropertyType)
        ids = list(stacking.value) if stacking else []
        net_name = d.intern_atom("_NET_WM_NAME")
        state_atom = d.intern_atom("_NET_WM_STATE")
        hidden = d.intern_atom("_NET_WM_STATE_HIDDEN")
        extents_atom = d.intern_atom("_NET_FRAME_EXTENTS")
        out = []
        for wid in reversed(ids):  # stacking order is bottom -> top
            win = d.create_resource_object("window", wid)
            try:
                state = win.get_full_property(state_atom, X.AnyPropertyType)
                if state and hidden in state.value:
                    continue
                geom = win.get_geometry()
                pos = win.translate_coords(root, 0, 0)
                x, y = -pos.x, -pos.y
                w, h = geom.width, geom.height
                ext = win.get_full_property(extents_atom, X.AnyPropertyType)
                if ext and len(ext.value) == 4:
                    left, right, top, bottom = ext.value
                    x, y, w, h = x - left, y - top, w + left + right, h + top + bottom
                name_prop = win.get_full_property(net_name, 0)
                title = name_prop.value.decode("utf-8", "replace") if name_prop else (win.get_wm_name() or "")
                if w > 1 and h > 1:
                    out.append((str(title), (x, y, w, h)))
            except Exception:  # noqa: BLE001 - windows can vanish meanwhile
                continue
        return out
    finally:
        d.close()


def scroll_wheel(x: int, y: int, clicks: int = -3):
    if not HAVE_XLIB:
        return
    d = display.Display()
    try:
        root = d.screen().root
        root.warp_pointer(int(x), int(y))
        button = 5 if clicks < 0 else 4
        for _ in range(abs(clicks)):
            xtest.fake_input(d, X.ButtonPress, button)
            xtest.fake_input(d, X.ButtonRelease, button)
        d.sync()
    finally:
        d.close()
