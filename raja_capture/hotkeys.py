"""Global hotkeys.

* Windows             : RegisterHotKey in a dedicated thread
* X11 (non-GNOME)     : pynput (optional dependency)
* GNOME (Wayland/X11) : custom keyboard shortcuts written via ``gsettings`` that run
                        ``raja-capture --<action>``; the running instance receives the
                        command through IPC.
"""

from __future__ import annotations

import ast
import shutil
import subprocess

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence

from .util import IS_WINDOWS, is_gnome, is_x11, quote_arg

# --------------------------------------------------------------------------- parsing


def _split(seq: str):
    ks = QKeySequence(seq)
    if ks.isEmpty():
        return None
    combo = ks[0]
    return combo.keyboardModifiers(), combo.key()


# Qt key -> (gtk name, pynput name, windows virtual key)
_SPECIAL = {
    Qt.Key_Print: ("Print", "print_screen", 0x2C),
    Qt.Key_Space: ("space", "space", 0x20),
    Qt.Key_Home: ("Home", "home", 0x24),
    Qt.Key_End: ("End", "end", 0x23),
    Qt.Key_Insert: ("Insert", "insert", 0x2D),
    Qt.Key_PageUp: ("Page_Up", "page_up", 0x21),
    Qt.Key_PageDown: ("Page_Down", "page_down", 0x22),
    Qt.Key_Pause: ("Pause", "pause", 0x13),
    Qt.Key_ScrollLock: ("Scroll_Lock", "scroll_lock", 0x91),
}


def _key_names(key):
    k = key.value if hasattr(key, "value") else int(key)
    if Qt.Key_A.value <= k <= Qt.Key_Z.value:
        ch = chr(k).lower()
        return ch, ch, k
    if Qt.Key_0.value <= k <= Qt.Key_9.value:
        ch = chr(k)
        return ch, ch, k
    if Qt.Key_F1.value <= k <= Qt.Key_F24.value:
        n = k - Qt.Key_F1.value + 1
        return f"F{n}", f"<f{n}>", 0x6F + n
    for qk, (gtk, pyn, vk) in _SPECIAL.items():
        if qk.value == k:
            return gtk, f"<{pyn}>", vk
    return None


def _mods(mods, names: dict) -> list:
    out = []
    for flag, key in ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                      (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "meta")):
        if mods & flag:
            out.append(names[key])
    return out


def to_gtk_accel(seq: str) -> str:
    parts = _split(seq)
    names = _key_names(parts[1]) if parts else None
    if not names:
        return ""
    m = _mods(parts[0], {"ctrl": "<Primary>", "alt": "<Alt>", "shift": "<Shift>", "meta": "<Super>"})
    return "".join(m) + names[0]


def to_pynput(seq: str) -> str:
    parts = _split(seq)
    names = _key_names(parts[1]) if parts else None
    if not names:
        return ""
    m = _mods(parts[0], {"ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "meta": "<cmd>"})
    return "+".join(m + [names[1]])


def to_windows(seq: str):
    parts = _split(seq)
    names = _key_names(parts[1]) if parts else None
    if not names:
        return None
    flags = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "meta": 0x8}
    m = sum(_mods(parts[0], flags))
    return m, names[2]


# --------------------------------------------------------------------------- windows


class _WinHotkeyThread(QThread):
    activated = Signal(str)

    def __init__(self, bindings: dict[str, str]):
        super().__init__()
        self.bindings = bindings
        self.failed: list[str] = []
        self._tid = None

    def run(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        ids = {}
        for i, (action, seq) in enumerate(self.bindings.items(), start=1):
            parsed = to_windows(seq)
            if not parsed:
                continue
            mods, vk = parsed
            if user32.RegisterHotKey(None, i, mods | 0x4000, vk):  # MOD_NOREPEAT
                ids[i] = action
            else:
                self.failed.append(action)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in ids:  # WM_HOTKEY
                self.activated.emit(ids[msg.wParam])
        for i in ids:
            user32.UnregisterHotKey(None, i)

    def stop(self):
        if self._tid is not None:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
        self.wait(2000)


# --------------------------------------------------------------------------- manager


class HotkeyManager(QObject):
    activated = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._win = None
        self._pynput = None
        self.status = ""

    @staticmethod
    def mode() -> str:
        if IS_WINDOWS:
            return "windows"
        if is_gnome():
            return "gnome"
        if is_x11():
            try:
                import pynput  # noqa: F401

                return "pynput"
            except ImportError:
                return "none"
        return "none"

    def reload(self):
        self.stop()
        bindings = {a: s for a, s in self.cfg.hotkeys().items() if s}
        mode = self.mode()
        if mode == "windows":
            self._win = _WinHotkeyThread(bindings)
            self._win.activated.connect(self.activated)
            self._win.start()
            self.status = "Shortcut global Windows aktif."
        elif mode == "pynput":
            from pynput import keyboard

            mapping = {}
            for action, seq in bindings.items():
                key = to_pynput(seq)
                if key:
                    mapping[key] = (lambda a=action: self.activated.emit(a))
            self._pynput = keyboard.GlobalHotKeys(mapping)
            self._pynput.start()
            self.status = "Shortcut global X11 (pynput) aktif."
        elif mode == "gnome":
            self.status = ("GNOME: shortcut dipasang ke Pengaturan Keyboard GNOME. Klik "
                           "'Terapkan ke GNOME' setelah mengubah shortcut.")
        else:
            self.status = ("Shortcut global tidak tersedia otomatis di desktop ini. Buat shortcut di "
                           "pengaturan desktop yang menjalankan: raja-capture --region (dst).")

    def stop(self):
        if self._win is not None:
            self._win.stop()
            self._win = None
        if self._pynput is not None:
            self._pynput.stop()
            self._pynput = None


# --------------------------------------------------------------------------- GNOME

MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PREFIX = "raja-capture-"


def _gsettings(*args) -> str:
    res = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "gsettings gagal")
    return res.stdout.strip()


def _custom_list() -> list[str]:
    raw = _gsettings("get", MEDIA_KEYS, "custom-keybindings")
    if raw.startswith("@as"):
        raw = raw[3:].strip()
    try:
        return list(ast.literal_eval(raw))
    except (ValueError, SyntaxError):
        return []


def _set_custom_list(paths: list[str]):
    _gsettings("set", MEDIA_KEYS, "custom-keybindings", str(paths))


def gnome_available() -> bool:
    return bool(shutil.which("gsettings")) and is_gnome()


def gnome_install(bindings: dict[str, str], labels: dict[str, str], launcher: list[str]) -> int:
    """Write GNOME custom shortcuts for every action; replaces earlier Raja entries."""
    gnome_uninstall()
    paths = _custom_list()
    count = 0
    cmd_base = " ".join(quote_arg(a) for a in launcher)
    for action, seq in bindings.items():
        accel = to_gtk_accel(seq) if seq else ""
        if not accel:
            continue
        flag = action.replace("_", "-")
        path = f"{CUSTOM_BASE}{PREFIX}{flag}/"
        rel = f"{MEDIA_KEYS}.custom-keybinding:{path}"
        _gsettings("set", rel, "name", f"Raja Capture: {labels.get(action, action)}")
        _gsettings("set", rel, "command", f"{cmd_base} --{flag}")
        _gsettings("set", rel, "binding", accel)
        paths.append(path)
        count += 1
    _set_custom_list(paths)
    return count


def gnome_uninstall() -> int:
    current = _custom_list()
    ours = [p for p in current if PREFIX in p]
    for p in ours:
        subprocess.run(["gsettings", "reset-recursively", f"{MEDIA_KEYS}.custom-keybinding:{p}"],
                       capture_output=True, timeout=10)
    if ours:
        _set_custom_list([p for p in current if PREFIX not in p])
    return len(ours)
