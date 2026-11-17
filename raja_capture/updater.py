"""Update checking and self-upgrade (blocking helpers; call from worker threads).

Install kinds and how they upgrade:

* ``windows-installer`` : download ``*-setup.exe`` and run it silently (it relaunches the app)
* ``appimage``          : download the new AppImage and atomically replace ``$APPIMAGE``
* ``deb``               : download the ``.deb`` and install it with ``pkexec apt-get``
* ``portable`` / ``source`` : no self-upgrade; open the release page instead
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from . import __version__
from .util import IS_LINUX, IS_WINDOWS

REPO = "firexsantos/raja-capture"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
USER_AGENT = "RajaCapture-Updater"


class UpdateError(Exception):
    pass


# --------------------------------------------------------------------------- versions


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


# --------------------------------------------------------------------------- release info


def fetch_latest(timeout: float = 15) -> dict:
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub menjawab {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Tidak bisa terhubung ke GitHub: {getattr(exc, 'reason', exc)}") from exc
    except ValueError as exc:
        raise UpdateError("Jawaban GitHub tidak valid") from exc
    tag = data.get("tag_name", "")
    return {
        "tag": tag,
        "version": ".".join(str(n) for n in parse_version(tag)),
        "name": data.get("name") or tag,
        "notes": data.get("body") or "",
        "url": data.get("html_url") or RELEASES_PAGE,
        "assets": [
            {"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
             "size": a.get("size", 0), "digest": a.get("digest") or ""}
            for a in data.get("assets", [])
        ],
    }


# --------------------------------------------------------------------------- install kind


def install_kind() -> str:
    if IS_LINUX and os.environ.get("APPIMAGE"):
        return "appimage"
    if not getattr(sys, "frozen", False):
        return "source"
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if IS_WINDOWS:
        has_uninstaller = any(n.lower().startswith("unins") and n.lower().endswith(".exe")
                              for n in os.listdir(exe_dir))
        return "windows-installer" if has_uninstaller else "portable"
    if IS_LINUX and exe_dir.startswith("/opt/raja-capture"):
        return "deb"
    return "portable"


ASSET_SUFFIX = {"windows-installer": "-setup.exe", "appimage": ".AppImage", "deb": "_amd64.deb"}


def pick_asset(kind: str, assets: list[dict]) -> dict | None:
    suffix = ASSET_SUFFIX.get(kind)
    if not suffix:
        return None
    return next((a for a in assets if a["name"].endswith(suffix)), None)


def can_self_update(kind: str | None = None) -> bool:
    return (kind or install_kind()) in ASSET_SUFFIX


# --------------------------------------------------------------------------- download


def download(asset: dict, dest_dir: str | None = None, progress=None, cancelled=None) -> str:
    """Download ``asset`` and verify its SHA-256 digest (when GitHub provides one)."""
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="raja-update-")
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, asset["name"])
    part = final + ".part"
    sha = hashlib.sha256()
    req = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Unduhan dibatalkan")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as exc:
        _silent_remove(part)
        raise UpdateError(f"Gagal mengunduh: {getattr(exc, 'reason', exc)}") from exc
    except BaseException:
        _silent_remove(part)
        raise
    digest = asset.get("digest", "")
    if digest.startswith("sha256:") and digest.split(":", 1)[1].lower() != sha.hexdigest():
        _silent_remove(part)
        raise UpdateError("File unduhan rusak (checksum SHA-256 tidak cocok). Coba lagi.")
    os.replace(part, final)
    return final


def _silent_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


def appimage_download_dir() -> str:
    """Download next to the running AppImage so the final rename is atomic."""
    target = os.environ.get("APPIMAGE", "")
    d = os.path.dirname(target)
    if d and os.access(d, os.W_OK):
        return os.path.join(d, ".raja-update")
    raise UpdateError(f"Folder AppImage tidak bisa ditulisi: {d}")


# --------------------------------------------------------------------------- apply


def apply_update(kind: str, path: str) -> list[str] | None:
    """Install the downloaded file. Returns the command to relaunch the app after this
    process exits (None when the installer relaunches it itself)."""
    if kind == "windows-installer":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          "/RESTARTAPPLICATIONS"], creationflags=flags, close_fds=True)
        return None
    if kind == "appimage":
        target = os.environ["APPIMAGE"]
        os.chmod(path, 0o755)
        os.replace(path, target)  # the running image keeps its old inode mounted
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        return [target]
    if kind == "deb":
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise UpdateError("pkexec tidak ditemukan. Pasang manual: sudo apt install " + path)
        res = subprocess.run([pkexec, "apt-get", "install", "-y", "--allow-downgrades", path],
                             capture_output=True, text=True)
        if res.returncode == 126 or res.returncode == 127:
            raise UpdateError("Otorisasi dibatalkan.")
        if res.returncode != 0:
            raise UpdateError("Instalasi gagal:\n" + (res.stderr or res.stdout)[-800:])
        return ["/opt/raja-capture/raja-capture"]
    raise UpdateError(f"Upgrade otomatis tidak didukung untuk instalasi '{kind}'")


def relaunch_after_exit(cmd: list[str]):
    """Start ``cmd`` once this process has exited (so single-instance IPC doesn't swallow it)."""
    if IS_WINDOWS:
        subprocess.Popen(cmd, creationflags=0x00000008, close_fds=True)
        return
    script = 'while kill -0 "$0" 2>/dev/null; do sleep 0.3; done; shift; exec "$@"'
    subprocess.Popen(["/bin/sh", "-c", script, str(os.getpid()), "_", *cmd],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
