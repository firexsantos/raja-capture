"""Sharing: upload (Imgur / custom HTTP server), email attachment, open-with, copy as file."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from PySide6.QtCore import QMimeData, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from .util import IS_LINUX, IS_MAC, IS_WINDOWS

USER_AGENT = "RajaCapture"
HISTORY_LIMIT = 50


class ShareError(Exception):
    pass


def share_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation) or os.path.expanduser("~/.cache")
    path = os.path.join(base, "share")
    os.makedirs(path, exist_ok=True)
    # Clean files older than a day so the cache does not grow forever.
    now = time.time()
    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if now - os.path.getmtime(full) > 86400:
                os.remove(full)
        except OSError:
            pass
    return path


# --------------------------------------------------------------------------- HTTP


def _multipart(field: str, filename: str, data: bytes, extra: dict | None = None):
    boundary = "----RajaCapture" + uuid.uuid4().hex
    lines = []
    for k, v in (extra or {}).items():
        lines += [f"--{boundary}".encode(), f'Content-Disposition: form-data; name="{k}"'.encode(), b"",
                  str(v).encode()]
    ctype = "image/png" if filename.lower().endswith(".png") else "application/octet-stream"
    lines += [f"--{boundary}".encode(),
              f'Content-Disposition: form-data; name="{field}"; filename="{filename}"'.encode(),
              f"Content-Type: {ctype}".encode(), b"", data, f"--{boundary}--".encode(), b""]
    return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


def _request(url: str, body: bytes, headers: dict, timeout=60) -> bytes:
    if not url.lower().startswith(("https://", "http://")):
        raise ShareError("URL harus diawali http:// atau https://")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode("utf-8", "replace")
        raise ShareError(f"Server menjawab {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ShareError(f"Gagal terhubung: {exc.reason}") from exc


def upload_imgur(path: str, client_id: str) -> dict:
    """Anonymous Imgur upload. Returns {'url', 'delete_url'}."""
    if not client_id:
        raise ShareError("Client ID Imgur belum diisi. Daftar gratis di https://api.imgur.com/oauth2/addclient "
                         "(pilih 'without callback') lalu isi di Pengaturan → Kirim.")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    body = urllib.parse.urlencode({"image": data, "type": "base64"}).encode()
    raw = _request("https://api.imgur.com/3/image", body, {
        "Authorization": f"Client-ID {client_id}",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        info = json.loads(raw)["data"]
        url = info["link"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ShareError(f"Jawaban Imgur tidak dikenali: {raw[:200]!r}") from exc
    delete = f"https://imgur.com/delete/{info['deletehash']}" if info.get("deletehash") else ""
    return {"url": url, "delete_url": delete, "service": "Imgur"}


def _json_path(obj, path: str):
    for part in [p for p in path.split(".") if p]:
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def upload_custom(path: str, url: str, field: str = "file", headers_json: str = "",
                  response_path: str = "") -> dict:
    """POST the file as multipart/form-data to any server (ShareX-style custom uploader)."""
    if not url:
        raise ShareError("URL server kustom belum diisi di Pengaturan → Kirim.")
    try:
        headers = json.loads(headers_json) if headers_json.strip() else {}
        if not isinstance(headers, dict):
            raise ValueError
    except ValueError as exc:
        raise ShareError("Header tambahan harus berupa objek JSON, mis. {\"Authorization\": \"Bearer x\"}") from exc
    with open(path, "rb") as f:
        body, ctype = _multipart(field or "file", os.path.basename(path), f.read())
    raw = _request(url, body, {**{str(k): str(v) for k, v in headers.items()}, "Content-Type": ctype})
    text = raw.decode("utf-8", "replace").strip()
    if response_path:
        try:
            link = str(_json_path(json.loads(text), response_path))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ShareError(f"Tidak menemukan '{response_path}' di jawaban server: {text[:200]}") from exc
    else:
        link = text.splitlines()[0] if text else ""
    if not link:
        raise ShareError("Server tidak mengembalikan link")
    return {"url": link, "delete_url": "", "service": urllib.parse.urlparse(url).netloc}


# --------------------------------------------------------------------------- history


def add_history(cfg, entry: dict):
    try:
        items = json.loads(cfg.get("upload_history") or "[]")
    except ValueError:
        items = []
    entry = {**entry, "time": time.strftime("%Y-%m-%d %H:%M")}
    items.insert(0, entry)
    cfg.set("upload_history", json.dumps(items[:HISTORY_LIMIT]))


def history(cfg) -> list[dict]:
    try:
        return json.loads(cfg.get("upload_history") or "[]")
    except ValueError:
        return []


# --------------------------------------------------------------------------- local sharing


def copy_file_to_clipboard(path: str):
    """Put the file itself on the clipboard (paste into chat apps / file manager)."""
    mime = QMimeData()
    url = QUrl.fromLocalFile(path)
    mime.setUrls([url])
    if IS_LINUX:
        mime.setData("x-special/gnome-copied-files", f"copy\n{url.toString()}".encode())
    QGuiApplication.clipboard().setMimeData(mime)


def email_with_attachment(path: str) -> str:
    """Open the mail client with the file attached when possible. Returns a status message."""
    if IS_LINUX and shutil.which("xdg-email"):
        subprocess.Popen(["xdg-email", "--subject", "Tangkapan layar", "--attach", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Membuka aplikasi email…"
    if IS_WINDOWS:
        try:
            _mapi_send(path)
            return "Membuka aplikasi email…"
        except Exception:  # noqa: BLE001 - fall back below
            pass
    QDesktopServices.openUrl(QUrl("mailto:?subject=Tangkapan%20layar"))
    reveal_in_folder(path)
    return "Aplikasi email dibuka; lampirkan file dari folder yang ditampilkan."


def _mapi_send(path: str):
    """Windows Simple MAPI: opens the default mail client with an attachment."""
    import ctypes
    from ctypes import wintypes

    class MapiFileDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("flFlags", wintypes.ULONG),
                    ("nPosition", wintypes.ULONG), ("lpszPathName", ctypes.c_char_p),
                    ("lpszFileName", ctypes.c_char_p), ("lpFileType", ctypes.c_void_p)]

    class MapiMessage(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("lpszSubject", ctypes.c_char_p),
                    ("lpszNoteText", ctypes.c_char_p), ("lpszMessageType", ctypes.c_char_p),
                    ("lpszDateReceived", ctypes.c_char_p), ("lpszConversationID", ctypes.c_char_p),
                    ("flFlags", wintypes.ULONG), ("lpOriginator", ctypes.c_void_p),
                    ("nRecipCount", wintypes.ULONG), ("lpRecips", ctypes.c_void_p),
                    ("nFileCount", wintypes.ULONG), ("lpFiles", ctypes.POINTER(MapiFileDesc))]

    enc = "mbcs"
    fd = MapiFileDesc(0, 0, 0xFFFFFFFF, path.encode(enc), os.path.basename(path).encode(enc), None)
    msg = MapiMessage(0, b"Tangkapan layar", b"", None, None, None, 0, None, 0, None, 1, ctypes.pointer(fd))
    mapi = ctypes.windll.mapi32
    MAPI_DIALOG, MAPI_LOGON_UI = 0x8, 0x1
    rc = mapi.MAPISendMail(0, 0, ctypes.byref(msg), MAPI_DIALOG | MAPI_LOGON_UI, 0)
    if rc not in (0, 1):  # 1 = user cancelled
        raise OSError(f"MAPISendMail gagal ({rc})")


def reveal_in_folder(path: str):
    if IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def open_with(program: str, path: str):
    if IS_MAC and program.endswith(".app"):
        subprocess.Popen(["open", "-a", program, path])
    else:
        subprocess.Popen([program, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000 if IS_WINDOWS else 0)


def external_programs(cfg) -> list[str]:
    try:
        progs = json.loads(cfg.get("external_programs") or "[]")
    except ValueError:
        progs = []
    return [p for p in progs if isinstance(p, str)]


def remember_program(cfg, program: str):
    progs = [p for p in external_programs(cfg) if p != program]
    cfg.set("external_programs", json.dumps([program, *progs][:8]))
