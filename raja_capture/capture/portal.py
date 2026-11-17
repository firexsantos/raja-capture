"""xdg-desktop-portal access (Screenshot + ScreenCast) for Wayland, via jeepney.

All functions here are blocking and must run in a worker thread.
"""

from __future__ import annotations

import os
import secrets
import time
import urllib.parse

from PySide6.QtGui import QImage

from .base import CaptureCancelled, CaptureError

try:
    from jeepney import DBusAddress, MatchRule, MessageType, message_bus, new_method_call
    from jeepney.io.blocking import Proxy, open_dbus_connection

    HAVE_JEEPNEY = True
except ImportError:  # pragma: no cover - non-linux
    HAVE_JEEPNEY = False

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJ_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT = "org.freedesktop.portal.Screenshot"
SCREENCAST = "org.freedesktop.portal.ScreenCast"


class PortalAccessDenied(CaptureError):
    """The portal refused (typically: permission dialog could not be shown/was denied)."""


APP_ID = "raja-capture"
PERM_BUS = "org.freedesktop.impl.portal.PermissionStore"
PERM_PATH = "/org/freedesktop/impl/portal/PermissionStore"


def registered_app_id() -> str:
    """App id the portal sees for us: 'raja-capture' when a .desktop file is installed
    (Qt registers it with the host Registry), otherwise '' (unregistered host app)."""
    dirs = [os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    for d in dirs:
        if d and os.path.exists(os.path.join(d, "applications", f"{APP_ID}.desktop")):
            return APP_ID
    return ""


def screenshot_permission(app_id: str | None = None) -> str | None:
    """'yes' / 'no' / None (never asked) for non-interactive screenshots."""
    if not HAVE_JEEPNEY:
        return "yes"
    app_id = registered_app_id() if app_id is None else app_id
    if not app_id:
        return "yes"  # unregistered host apps are allowed without a dialog
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception:  # noqa: BLE001
        return None
    try:
        msg = new_method_call(DBusAddress(PERM_PATH, bus_name=PERM_BUS,
                                          interface="org.freedesktop.impl.portal.PermissionStore"),
                              "Lookup", "ss", ("screenshot", "screenshot"))
        reply = conn.send_and_get_reply(msg, timeout=5)
        if reply.header.message_type == MessageType.error:
            return None
        perms = reply.body[0]
        values = perms.get(app_id)
        return values[0] if values else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def reset_screenshot_permission(app_id: str = APP_ID) -> bool:
    """Forget a stored yes/no so GNOME asks again (does not grant anything)."""
    conn = open_dbus_connection(bus="SESSION")
    try:
        msg = new_method_call(DBusAddress(PERM_PATH, bus_name=PERM_BUS,
                                          interface="org.freedesktop.impl.portal.PermissionStore"),
                              "DeletePermission", "sss", ("screenshot", "screenshot", app_id))
        reply = conn.send_and_get_reply(msg, timeout=5)
        return reply.header.message_type != MessageType.error
    finally:
        conn.close()


def _addr(interface: str, path: str = OBJ_PATH):
    return DBusAddress(path, bus_name=BUS_NAME, interface=interface)


def _token() -> str:
    return "raja_" + secrets.token_hex(6)


def _check_reply(reply):
    if reply.header.message_type == MessageType.error:
        name = reply.header.fields.get(4, "error")  # HeaderFields.error_name
        detail = reply.body[0] if reply.body else ""
        raise CaptureError(f"Portal error {name}: {detail}")
    return reply


def _request(conn, interface: str, method: str, signature: str, args: tuple, token: str, timeout=300):
    """Call a portal method that returns a Request handle and wait for its Response."""
    sender = conn.unique_name.lstrip(":").replace(".", "_")
    path = f"{OBJ_PATH}/request/{sender}/{token}"
    rule = MatchRule(
        type="signal",
        interface="org.freedesktop.portal.Request",
        member="Response",
        path=path,
    )
    Proxy(message_bus, conn).AddMatch(rule)
    with conn.filter(rule) as queue:
        msg = new_method_call(_addr(interface), method, signature, args)
        _check_reply(conn.send_and_get_reply(msg, timeout=30))
        try:
            response = conn.recv_until_filtered(queue, timeout=timeout)
        except TimeoutError as exc:
            raise CaptureError("Portal tidak merespons (timeout)") from exc
    code, results = response.body
    if code == 1:
        raise CaptureCancelled()
    if code != 0:
        raise CaptureError(f"Portal {method} gagal (kode {code})")
    return results


def portal_available() -> bool:
    if not HAVE_JEEPNEY:
        return False
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception:  # noqa: BLE001
        return False
    try:
        msg = new_method_call(
            DBusAddress(OBJ_PATH, bus_name=BUS_NAME, interface="org.freedesktop.DBus.Properties"),
            "Get",
            "ss",
            (SCREENSHOT, "version"),
        )
        reply = conn.send_and_get_reply(msg, timeout=5)
        return reply.header.message_type != MessageType.error
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


def screenshot(interactive: bool = False, timeout: float = 300) -> QImage:
    """Take a screenshot through the portal and return it as a QImage."""
    if not HAVE_JEEPNEY:
        raise CaptureError("Paket 'jeepney' belum terpasang")
    conn = open_dbus_connection(bus="SESSION")
    try:
        token = _token()
        options = {
            "handle_token": ("s", token),
            "interactive": ("b", bool(interactive)),
            "modal": ("b", True),
        }
        try:
            results = _request(conn, SCREENSHOT, "Screenshot", "sa{sv}", ("", options), token, timeout)
        except CaptureError as exc:
            if not interactive and "(kode 2)" in str(exc):
                raise PortalAccessDenied(
                    "GNOME belum mengizinkan Raja Capture mengambil screenshot.") from exc
            raise
    finally:
        conn.close()

    uri = results.get("uri", (None, ""))[1]
    path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
    if not path or not os.path.exists(path):
        raise CaptureError("Portal tidak mengembalikan file gambar")
    img = QImage(path)
    if img.isNull():
        raise CaptureError(f"Gagal membaca gambar dari portal: {path}")
    img = img.convertToFormat(QImage.Format_RGB32)
    # The portal writes a temporary file for us (often in ~/Pictures); remove it
    # so the user's folder is not littered. Only delete files created just now.
    try:
        if time.time() - os.path.getmtime(path) < 120:
            os.remove(path)
    except OSError:
        pass
    return img


class ScreenCastSession:
    """A ScreenCast portal session that yields a PipeWire fd + node id."""

    SOURCE_MONITOR = 1
    SOURCE_WINDOW = 2

    def __init__(self):
        if not HAVE_JEEPNEY:
            raise CaptureError("Paket 'jeepney' belum terpasang")
        self.conn = open_dbus_connection(bus="SESSION", enable_fds=True)
        self.session_handle: str | None = None
        self.fd: int | None = None
        self.restore_token: str | None = None

    def _cursor_mode(self, want_cursor: bool) -> int:
        try:
            msg = new_method_call(
                DBusAddress(OBJ_PATH, bus_name=BUS_NAME, interface="org.freedesktop.DBus.Properties"),
                "Get",
                "ss",
                (SCREENCAST, "AvailableCursorModes"),
            )
            reply = _check_reply(self.conn.send_and_get_reply(msg, timeout=5))
            modes = reply.body[0][1]
        except Exception:  # noqa: BLE001
            modes = 1
        if want_cursor and modes & 2:
            return 2  # embedded
        return 1  # hidden

    def start(self, source_types: int = 1, cursor: bool = True, restore_token: str | None = None,
              persist: bool = False):
        """Run the portal handshake. Returns (node_id, (width, height) or None)."""
        t = _token()
        res = _request(
            self.conn, SCREENCAST, "CreateSession", "a{sv}",
            ({"handle_token": ("s", t), "session_handle_token": ("s", _token())},), t,
        )
        self.session_handle = res["session_handle"][1]

        t = _token()
        opts = {
            "handle_token": ("s", t),
            "types": ("u", source_types),
            "multiple": ("b", False),
            "cursor_mode": ("u", self._cursor_mode(cursor)),
        }
        if persist:
            opts["persist_mode"] = ("u", 2)
        if restore_token:
            opts["restore_token"] = ("s", restore_token)
        _request(self.conn, SCREENCAST, "SelectSources", "oa{sv}", (self.session_handle, opts), t)

        t = _token()
        res = _request(self.conn, SCREENCAST, "Start", "osa{sv}",
                       (self.session_handle, "", {"handle_token": ("s", t)}), t)
        streams = res.get("streams", (None, []))[1]
        if not streams:
            raise CaptureError("Portal tidak memberikan stream video")
        self.restore_token = res.get("restore_token", (None, None))[1]
        node_id, props = streams[0]
        size = props.get("size", (None, None))[1]

        msg = new_method_call(_addr(SCREENCAST), "OpenPipeWireRemote", "oa{sv}", (self.session_handle, {}))
        reply = _check_reply(self.conn.send_and_get_reply(msg, timeout=30))
        self.fd = reply.body[0].to_raw_fd()
        return node_id, (tuple(size) if size else None)

    def close(self):
        try:
            if self.session_handle:
                msg = new_method_call(
                    DBusAddress(self.session_handle, bus_name=BUS_NAME,
                                interface="org.freedesktop.portal.Session"),
                    "Close",
                )
                self.conn.send_and_get_reply(msg, timeout=5)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.session_handle = None
            try:
                self.conn.close()
            except Exception:  # noqa: BLE001
                pass
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None


REMOTE = "org.freedesktop.portal.RemoteDesktop"


def remote_desktop_available() -> bool:
    if not HAVE_JEEPNEY:
        return False
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception:  # noqa: BLE001
        return False
    try:
        msg = new_method_call(
            DBusAddress(OBJ_PATH, bus_name=BUS_NAME, interface="org.freedesktop.DBus.Properties"),
            "Get", "ss", (REMOTE, "AvailableDeviceTypes"))
        reply = conn.send_and_get_reply(msg, timeout=5)
        return reply.header.message_type != MessageType.error and bool(reply.body[0][1] & 2)
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


class RemoteDesktopSession:
    """RemoteDesktop portal session used to scroll content during scrolling capture.

    A monitor stream is attached only so the pointer can be moved to the capture area
    (absolute motion needs a stream); no video is read from it.
    """

    def __init__(self):
        if not HAVE_JEEPNEY:
            raise CaptureError("Paket 'jeepney' belum terpasang")
        self.conn = open_dbus_connection(bus="SESSION")
        self.session_handle: str | None = None
        self.stream: tuple[int, dict] | None = None
        self.restore_token: str | None = None

    def start(self, restore_token: str | None = None):
        t = _token()
        res = _request(self.conn, REMOTE, "CreateSession", "a{sv}",
                       ({"handle_token": ("s", t), "session_handle_token": ("s", _token())},), t)
        self.session_handle = res["session_handle"][1]
        t = _token()
        opts = {"handle_token": ("s", t), "types": ("u", 2), "persist_mode": ("u", 2)}
        if restore_token:
            opts["restore_token"] = ("s", restore_token)
        _request(self.conn, REMOTE, "SelectDevices", "oa{sv}", (self.session_handle, opts), t)
        t = _token()
        _request(self.conn, SCREENCAST, "SelectSources", "oa{sv}",
                 (self.session_handle, {"handle_token": ("s", t), "types": ("u", 1),
                                        "multiple": ("b", False)}), t)
        t = _token()
        res = _request(self.conn, REMOTE, "Start", "osa{sv}",
                       (self.session_handle, "", {"handle_token": ("s", t)}), t)
        devices = res.get("devices", (None, 0))[1]
        if not devices & 2:
            raise CaptureError("Izin mengontrol pointer tidak diberikan")
        streams = res.get("streams", (None, []))[1]
        if streams:
            node, props = streams[0]
            self.stream = (node, {k: v[1] for k, v in props.items()})
        self.restore_token = res.get("restore_token", (None, None))[1]
        return self.stream

    def _notify(self, method: str, signature: str, args: tuple):
        msg = new_method_call(_addr(REMOTE), method, signature, args)
        _check_reply(self.conn.send_and_get_reply(msg, timeout=5))

    def move_pointer(self, x: float, y: float):
        """Move the pointer to (x, y) in the attached stream's coordinate space."""
        if not self.stream:
            return
        self._notify("NotifyPointerMotionAbsolute", "oa{sv}udd",
                     (self.session_handle, {}, self.stream[0], float(x), float(y)))

    def scroll(self, steps: int):
        """Discrete vertical wheel steps; positive scrolls content down."""
        self._notify("NotifyPointerAxisDiscrete", "oa{sv}ui", (self.session_handle, {}, 0, int(steps)))

    def close(self):
        try:
            if self.session_handle:
                msg = new_method_call(
                    DBusAddress(self.session_handle, bus_name=BUS_NAME,
                                interface="org.freedesktop.portal.Session"), "Close")
                self.conn.send_and_get_reply(msg, timeout=5)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.session_handle = None
            try:
                self.conn.close()
            except Exception:  # noqa: BLE001
                pass
