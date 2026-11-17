import os
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
