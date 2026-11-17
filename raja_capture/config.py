"""Persistent settings (QSettings) and output-file naming."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import QSettings, QStandardPaths

# (action id, label, default shortcut in QKeySequence portable text)
ACTIONS = [
    ("full", "Tangkap layar penuh", "Ctrl+Alt+1"),
    ("window", "Tangkap jendela", "Ctrl+Alt+2"),
    ("region", "Tangkap area", "Ctrl+Alt+3"),
    ("scroll", "Tangkap scroll (halaman panjang)", "Ctrl+Alt+4"),
    ("record_region", "Rekam area layar", "Ctrl+Alt+5"),
    ("record_full", "Rekam layar penuh", "Ctrl+Alt+6"),
    ("color", "Pemilih warna", "Ctrl+Alt+7"),
    ("ruler", "Penggaris layar", "Ctrl+Alt+8"),
    ("ocr", "OCR area (ambil teks)", "Ctrl+Alt+9"),
]
ACTION_LABELS = {a: label for a, label, _ in ACTIONS}

AFTER_CAPTURE = [
    ("editor", "Buka di editor"),
    ("save", "Simpan otomatis"),
    ("clipboard", "Salin ke clipboard"),
    ("save_clipboard", "Simpan + salin ke clipboard"),
]

IMAGE_FORMATS = ["png", "jpg", "bmp", "webp"]


def _default_output_dir() -> str:
    pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
    return os.path.join(pics or os.path.expanduser("~"), "RajaCapture")


def _default_video_dir() -> str:
    vids = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
    return os.path.join(vids or os.path.expanduser("~"), "RajaCapture")


DEFAULTS = {
    "output_dir": _default_output_dir(),
    "video_dir": _default_video_dir(),
    "filename_pattern": "Raja_%Y-%m-%d_%H-%M-%S",
    "image_format": "png",
    "jpeg_quality": 92,
    "after_capture": "editor",
    "delay": 0,
    "hide_toolbar": True,
    "record_fps": 30,
    "record_cursor": True,
    "record_audio": "none",
    "audio_mic_device": "",
    "audio_system_device": "",
    "screencast_token": "",
    "ocr_lang": "eng",
    "tesseract_path": "",
    "ffmpeg_path": "",
    "scroll_interval_ms": 700,
    "scroll_auto": True,
    "first_run_done": False,
    "check_updates": True,
    "last_update_check": 0,
    "skipped_version": "",
    "imgur_client_id": "",
    "imgur_confirmed": False,
    "custom_upload_url": "",
    "custom_upload_field": "file",
    "custom_upload_headers": "",
    "custom_upload_response": "",
    "upload_history": "[]",
    "external_programs": "[]",
    "editor_color": "#e53935",
    "editor_width": 3,
    "editor_font_size": 24,
}


class Config:
    def __init__(self):
        self._s = QSettings("RajaCapture", "RajaCapture")

    def get(self, key: str):
        default = DEFAULTS.get(key)
        value = self._s.value(key, default)
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes")
            return bool(value)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value if value is not None else default

    def set(self, key: str, value):
        self._s.setValue(key, value)

    # hotkeys -------------------------------------------------------------
    def hotkey(self, action: str) -> str:
        default = next((d for a, _, d in ACTIONS if a == action), "")
        return str(self._s.value(f"hotkeys/{action}", default) or "")

    def set_hotkey(self, action: str, seq: str):
        self._s.setValue(f"hotkeys/{action}", seq)

    def hotkeys(self) -> dict[str, str]:
        return {a: self.hotkey(a) for a, _, _ in ACTIONS}

    def sync(self):
        self._s.sync()


def next_filename(directory: str, pattern: str, ext: str) -> str:
    """Build a unique path from a strftime pattern inside ``directory``."""
    os.makedirs(directory, exist_ok=True)
    try:
        base = time.strftime(pattern or DEFAULTS["filename_pattern"])
    except ValueError:
        base = time.strftime(DEFAULTS["filename_pattern"])
    base = "".join(c for c in base if c not in '<>:"/\\|?*') or "Raja"
    path = os.path.join(directory, f"{base}.{ext}")
    n = 2
    while os.path.exists(path):
        path = os.path.join(directory, f"{base}_{n}.{ext}")
        n += 1
    return path
