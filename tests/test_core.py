import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Keep tests away from the user's real settings.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="raja-test-cfg-")

import numpy as np
import pytest
from PySide6.QtCore import QLineF, QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from raja_capture.stitch import Stitcher, find_shift, static_rows


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _page(height=3000, width=400, seed=1):
    rng = np.random.default_rng(seed)
    page = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    # add some horizontal structure like text lines
    page[::17] = 255
    return page


def test_find_shift_basic():
    page = _page()
    a, b = page[100:500], page[160:560]
    assert find_shift(a, b) == 60


def test_stitch_full_page_with_header_footer():
    page = _page(2000)
    header = np.full((40, 400, 3), 30, np.uint8)
    footer = np.full((30, 400, 3), 220, np.uint8)
    view_h = 400
    st = Stitcher()
    for off in range(0, 2000 - view_h + 1, 90):
        frame = np.vstack([header, page[off:off + view_h], footer])
        st.add(frame)
    # final frame exactly at the bottom
    st.add(np.vstack([header, page[2000 - view_h:2000], footer]))
    res = st.result()
    expected = np.vstack([header, page, footer])
    assert res.shape == expected.shape
    assert np.array_equal(res, expected)


def test_static_rows():
    a = _page(100)
    b = a.copy()
    b[10:90] = 0
    assert static_rows(a, b) == (10, 10)


def test_no_movement_is_same():
    page = _page()
    st = Stitcher()
    st.add(page[:300])
    assert st.add(page[:300].copy()) == "same"


def test_hotkey_conversion(qapp):
    from raja_capture.hotkeys import to_gtk_accel, to_pynput, to_windows

    assert to_gtk_accel("Ctrl+Alt+3") == "<Primary><Alt>3"
    assert to_gtk_accel("Shift+Print") == "<Shift>Print"
    assert to_pynput("Ctrl+Shift+F5") == "<ctrl>+<shift>+<f5>"
    assert to_windows("Ctrl+Alt+R") == (0x3, ord("R"))


def test_quote_arg():
    from raja_capture.util import quote_arg

    assert quote_arg("/usr/bin/x") == "/usr/bin/x"
    assert quote_arg("/home/a/RAJA CAPTURE/x") == '"/home/a/RAJA CAPTURE/x"'


def test_array_roundtrip(qapp):
    from raja_capture.util import array_to_qimage, qimage_to_array

    arr = _page(37, 53)
    assert np.array_equal(qimage_to_array(array_to_qimage(arr)), arr)


class _FakeApp:
    def __init__(self):
        from raja_capture.config import Config

        self.cfg = Config()

    def start_capture(self, *_):
        pass


def _img(w=300, h=200):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("white"))
    return img


def test_editor_draw_crop_undo_save(qapp, tmp_path):
    from raja_capture.ui.editor import EditorWindow
    from raja_capture.ui.items import ArrowItem

    ed = EditorWindow(_FakeApp(), _img())
    for tool in ("rect", "arrow", "highlight", "pixelate", "ellipse", "line", "pen"):
        it = ed.begin_shape(tool, QPointF(10, 10))
        ed.update_shape(it, tool, QPointF(10, 10), QPointF(100, 80), False)
        ed.end_shape(it, tool)
    ed.create_step(QPointF(150, 150))
    ed.create_step(QPointF(170, 150))
    assert len(ed.annotations()) == 9
    assert sorted(i.number for i in ed.annotations() if i.kind == "step") == [1, 2]

    # style change on selection is undoable
    arrow = next(i for i in ed.annotations() if isinstance(i, ArrowItem))
    arrow.setSelected(True)
    ed.set_color(QColor("#00ff00"))
    assert arrow.get_style()["color"].name() == "#00ff00"
    ed.undo.undo()
    assert arrow.get_style()["color"].name() != "#00ff00"

    # rendered image contains the red rectangle border
    img = ed.render_image()
    assert img.size().width() == 300
    assert img.pixelColor(10, 50).red() > 150

    ed.crop(QRectF(5, 5, 100, 50))
    assert ed.base.pixmap().width() == 100
    assert ed.scene.sceneRect().width() == 100
    ed.undo.undo()
    assert ed.base.pixmap().width() == 300

    ed.rotate(90)
    assert ed.base.pixmap().width() == 200 and not ed.annotations()
    ed.undo.undo()
    assert ed.base.pixmap().width() == 300 and len(ed.annotations()) == 9

    ed.scene.clearSelection()
    ed.select_all()
    ed.delete_selected()
    assert not ed.annotations()
    ed.undo.undo()
    assert len(ed.annotations()) == 9

    for ext in ("png", "jpg", "pdf"):
        path = str(tmp_path / f"out.{ext}")
        assert ed._write(path)
        assert os.path.getsize(path) > 0
    ed._never_saved = False
    ed.undo.setClean()
    ed.close()


def test_overlay_region(qapp):
    from raja_capture.capture.base import DesktopShot, virtual_geometry
    from raja_capture.ui.overlay import OverlayController

    vg = virtual_geometry()
    shot = DesktopShot(_img(vg.width() * 2, vg.height() * 2), vg)  # simulate HiDPI 2x
    ctrl = OverlayController(shot, "region")
    got = []
    ctrl.regionSelected.connect(lambda r, l, s: got.append((r, l)))
    ctrl.start()
    ov = ctrl.overlays[0]
    ov.grab()  # paints without crashing
    r = QRect(10, 20, 100, 50)
    ctrl.finish_region(ov.local_to_img_rect(r), r.translated(ov.geo.topLeft()), ov.screen_)
    img_rect, logical = got[0]
    assert img_rect == QRect(20, 40, 200, 100)
    assert shot.logical_to_image(logical) == img_rect


def test_overlay_modes_paint(qapp):
    from raja_capture.capture.base import DesktopShot, WindowInfo, virtual_geometry
    from raja_capture.ui.overlay import OverlayController

    vg = virtual_geometry()
    shot = DesktopShot(_img(vg.width(), vg.height()), vg, [WindowInfo("w", QRect(5, 5, 50, 50))])
    for mode in ("window", "color", "ruler"):
        ctrl = OverlayController(shot, mode)
        ctrl.start()
        ov = ctrl.overlays[0]
        ov.mouse = ov.rect().center()
        ov.hover_rect = ov.window_at(QRect(10, 10, 1, 1).topLeft())
        ov.lines.append((QPointF(0, 0), QPointF(30, 40)))
        ov.grab()
        ctrl.cancel()


def test_next_filename(tmp_path):
    from raja_capture.config import next_filename

    a = next_filename(str(tmp_path), "shot", "png")
    open(a, "w").close()
    b = next_filename(str(tmp_path), "shot", "png")
    assert a != b and b.endswith("shot_2.png")


def test_resize_handles(qapp):
    from raja_capture.ui.editor import EditorWindow
    from raja_capture.ui.items import ArrowItem, HandleItem, RectItem

    ed = EditorWindow(_FakeApp(), _img())
    rect = RectItem(QRectF(10, 10, 50, 40))
    ed.scene.addItem(rect)
    rect.setSelected(True)
    handles = [h for h in ed.scene.items() if isinstance(h, HandleItem)]
    assert len(handles) == 8
    br = next(h for h in handles if h.key == "br")
    start = rect.get_geometry()
    rect.move_control("br", QPointF(120, 90), start)
    ed._push_geometry(rect, start, rect.get_geometry())
    assert rect.rect() == QRectF(10, 10, 110, 80)
    ed.undo.undo()
    assert rect.rect() == QRectF(10, 10, 50, 40)
    assert br.pos() == QPointF(60, 50)  # handles follow undo

    # dragging a corner past the opposite edge flips cleanly
    rect.move_control("tl", QPointF(100, 100), rect.get_geometry())
    assert rect.rect() == QRectF(60, 50, 40, 50)

    arrow = ArrowItem(QLineF(0, 0, 50, 0))
    ed.scene.addItem(arrow)
    ed.scene.clearSelection()
    arrow.setSelected(True)
    assert len([h for h in ed.scene.items() if isinstance(h, HandleItem)]) == 2
    arrow.move_control("p2", QPointF(40, 38), arrow.get_geometry(), shift=True)
    l = arrow.line()
    assert abs(l.dx() - l.dy()) < 1e-6  # snapped to 45°

    ed.scene.clearSelection()
    assert not [h for h in ed.scene.items() if isinstance(h, HandleItem)]
    img = ed.render_image()  # handles never appear in exports
    assert img.width() == 300
    ed._never_saved = False
    ed.undo.setClean()
    ed.close()


def test_custom_upload_local_server(qapp, tmp_path):
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from raja_capture import share

    received = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received["auth"] = self.headers.get("Authorization")
            received["has_file"] = b'name="image"; filename="pic.png"' in body and b"PNGDATA" in body
            out = _json.dumps({"data": {"url": "http://x/abc.png"}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    f = tmp_path / "pic.png"
    f.write_bytes(b"PNGDATA")
    res = share.upload_custom(str(f), f"http://127.0.0.1:{srv.server_port}/up", "image",
                              '{"Authorization": "Bearer t"}', "data.url")
    srv.server_close()
    assert res["url"] == "http://x/abc.png"
    assert received == {"auth": "Bearer t", "has_file": True}

    with pytest.raises(share.ShareError):
        share.upload_custom(str(f), "ftp://nope", "file", "", "")
    with pytest.raises(share.ShareError):
        share.upload_imgur(str(f), "")


def test_share_helpers(qapp, tmp_path):
    from raja_capture import share
    from raja_capture.config import Config

    cfg = Config()
    share.add_history(cfg, {"url": "http://a", "service": "X", "delete_url": ""})
    assert share.history(cfg)[0]["url"] == "http://a"
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    share.copy_file_to_clipboard(str(f))
    urls = qapp.clipboard().mimeData().urls()
    assert urls and urls[0].toLocalFile() == str(f)
    share.remember_program(cfg, "/usr/bin/gimp")
    assert share.external_programs(cfg)[0] == "/usr/bin/gimp"


def test_settings_dialog_builds(qapp):
    from raja_capture.capture import create_backend
    from raja_capture.config import Config
    from raja_capture.hotkeys import HotkeyManager
    from raja_capture.ui.settings_dialog import SettingsDialog

    class A:
        pass

    a = A()
    a.cfg = Config()
    a.backend = create_backend()
    a.hotkeys = HotkeyManager(a.cfg)
    dlg = SettingsDialog(a)
    dlg.audio.setCurrentIndex(dlg.audio.findData("both"))
    dlg.accept()
    assert a.cfg.get("record_audio") == "both"


def test_magnifier_not_dimmed_during_selection(qapp):
    from raja_capture.capture.base import DesktopShot, virtual_geometry
    from raja_capture.ui.overlay import OverlayController

    vg = virtual_geometry()
    img = _img(vg.width(), vg.height())  # white
    ctrl = OverlayController(DesktopShot(img, vg), "region")
    ctrl.start()
    ov = ctrl.overlays[0]
    ov.origin, ov.cur, ov.mouse = QRect(20, 20, 1, 1).topLeft(), QRect(100, 100, 1, 1).topLeft(), \
        QRect(100, 100, 1, 1).topLeft()
    g = ov.grab().toImage()
    assert g.pixelColor(134, 134).name() == "#ffffff"
    ctrl.cancel()


# ----------------------------------------------------------------------------- updater

def test_version_compare():
    from raja_capture import updater

    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("0.4") == (0, 4, 0)
    assert updater.is_newer("v0.10.0", "0.9.9")
    assert not updater.is_newer("v0.3.0", "0.3.0")
    assert not updater.is_newer("0.2.9", "0.3.0")


def test_pick_asset_and_kind(monkeypatch):
    from raja_capture import updater

    assets = [{"name": n, "url": "u", "size": 1, "digest": ""} for n in (
        "raja-capture_0.3.0_amd64.deb", "RajaCapture-0.3.0-setup.exe",
        "RajaCapture-0.3.0-windows-portable.zip", "RajaCapture-0.3.0-x86_64.AppImage")]
    assert updater.pick_asset("deb", assets)["name"].endswith(".deb")
    assert updater.pick_asset("windows-installer", assets)["name"].endswith("setup.exe")
    assert updater.pick_asset("appimage", assets)["name"].endswith(".AppImage")
    assert updater.pick_asset("source", assets) is None
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert updater.install_kind() == "source"
    monkeypatch.setenv("APPIMAGE", "/tmp/x.AppImage")
    assert updater.install_kind() == "appimage"


def _serve_bytes(payload: bytes):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_download_verifies_sha256_and_appimage_replace(tmp_path, monkeypatch):
    import hashlib

    from raja_capture import updater

    payload = b"#!/bin/sh\necho new\n" * 1000
    srv = _serve_bytes(payload)
    url = f"http://127.0.0.1:{srv.server_port}/RajaCapture-9.9.9-x86_64.AppImage"
    good = {"name": "RajaCapture-9.9.9-x86_64.AppImage", "url": url, "size": len(payload),
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
    seen = []
    path = updater.download(good, str(tmp_path / "dl"), progress=lambda d, t: seen.append((d, t)))
    assert open(path, "rb").read() == payload and seen[-1] == (len(payload), len(payload))

    bad = dict(good, digest="sha256:" + "0" * 64)
    with pytest.raises(updater.UpdateError):
        updater.download(bad, str(tmp_path / "dl2"))
    assert not list((tmp_path / "dl2").iterdir())  # partial file removed

    # AppImage: atomic replace of the running image + relaunch command
    old = tmp_path / "Raja.AppImage"
    old.write_bytes(b"old")
    monkeypatch.setenv("APPIMAGE", str(old))
    dest = updater.appimage_download_dir()
    new = updater.download(good, dest)
    cmd = updater.apply_update("appimage", new)
    srv.shutdown()
    assert cmd == [str(old)]
    assert old.read_bytes() == payload and os.access(old, os.X_OK)
    assert not os.path.exists(dest)


def test_update_dialog_builds(qapp):
    from raja_capture.ui.update_dialog import UpdateDialog

    info = {"version": "9.9.9", "notes": "### Added\n- Something new", "url": "http://x", "assets": []}
    dlg = UpdateDialog(info, "appimage")
    assert dlg.auto
    dlg2 = UpdateDialog(info, "source")
    assert not dlg2.auto


def test_changelog_in_sync():
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = subprocess.run([sys.executable, os.path.join(root, "packaging", "changelog.py"), "check"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout


def test_registered_app_id(tmp_path, monkeypatch):
    from raja_capture.capture import portal

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "sys"))
    assert portal.registered_app_id() == ""
    assert portal.screenshot_permission("") == "yes"
    apps = tmp_path / "sys" / "applications"
    apps.mkdir(parents=True)
    (apps / "raja-capture.desktop").write_text("[Desktop Entry]\n")
    assert portal.registered_app_id() == "raja-capture"
