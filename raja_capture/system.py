"""Desktop integration: launcher command, .desktop entry, autostart."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .util import IS_LINUX, IS_WINDOWS, quote_arg

ASSET_ICON = Path(__file__).parent / "assets" / "raja-capture.svg"


def launcher_argv() -> list[str]:
    """Command that starts Raja Capture (used for shortcuts / autostart)."""
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"]]  # stable path; sys.executable lives in a temp mount
    if getattr(sys, "frozen", False):
        return [sys.executable]
    script = Path(sys.executable).with_name("raja-capture" + (".exe" if IS_WINDOWS else ""))
    if script.exists():
        return [str(script)]
    return [sys.executable, "-m", "raja_capture"]


def _installed_icon() -> str:
    """Copy the icon to the user's icon theme so .desktop files survive AppImage unmounts."""
    if not IS_LINUX:
        return str(ASSET_ICON)
    target = Path.home() / ".local/share/icons/hicolor/scalable/apps/raja-capture.svg"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ASSET_ICON.read_bytes())
        return "raja-capture"
    except OSError:
        return str(ASSET_ICON)


def _desktop_entry(extra_args: str = "") -> str:
    exec_line = " ".join(quote_arg(a) for a in launcher_argv())
    if extra_args:
        exec_line += " " + extra_args
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Raja Capture\n"
        "GenericName=Screen Capture\n"
        "Comment=Tangkap layar, anotasi, dan rekam layar\n"
        f"Exec={exec_line}\n"
        f"Icon={_installed_icon()}\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "Keywords=screenshot;capture;screen;record;ocr;\n"
        "StartupNotify=false\n"
    )


def install_desktop_entry() -> str:
    if not IS_LINUX:
        raise RuntimeError("Hanya untuk Linux")
    path = Path.home() / ".local/share/applications/raja-capture.desktop"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_desktop_entry(), encoding="utf-8")
    return str(path)


def _autostart_path() -> Path:
    return Path.home() / ".config/autostart/raja-capture.desktop"


def autostart_enabled() -> bool:
    if IS_WINDOWS:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "RajaCapture")
                return True
        except OSError:
            return False
    if IS_LINUX:
        return _autostart_path().exists()
    return False


def set_autostart(enabled: bool):
    if IS_WINDOWS:
        import subprocess
        import winreg

        cmd = subprocess.list2cmdline(launcher_argv() + ["--tray"])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "RajaCapture", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "RajaCapture")
                except OSError:
                    pass
        return
    if IS_LINUX:
        path = _autostart_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_desktop_entry("--tray"), encoding="utf-8")
        elif path.exists():
            os.remove(path)
        return
    raise RuntimeError("Autostart belum didukung di platform ini")
