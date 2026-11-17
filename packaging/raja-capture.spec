# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec - build with:  python -m PyInstaller packaging/raja-capture.spec
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_WIN = sys.platform.startswith("win")

hidden = collect_submodules("raja_capture") + [
    "PySide6.QtSvg",  # SVG icon rendering
    "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
]
if sys.platform.startswith("linux"):
    hidden += collect_submodules("jeepney")

# Qt modules we never use - keeps the bundle much smaller.
excludes = [
    "tkinter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

icon_file = os.path.join(SPECPATH, "build", "raja-capture.ico")

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "raja_capture", "assets"), "raja_capture/assets")],
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="raja-capture",
    console=False,
    icon=icon_file if (IS_WIN and os.path.exists(icon_file)) else None,
    version=None,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="raja-capture")
