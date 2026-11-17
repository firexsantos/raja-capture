"""Test session setup.

PySide6 can segfault at interpreter shutdown when Qt objects are destroyed in
arbitrary GC order. Close every widget while Qt is still alive, then exit with
pytest's status code without running the fragile interpreter teardown.
"""

import os
import sys

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            for w in QApplication.topLevelWidgets():
                w.hide()
                w.deleteLater()
            app.processEvents()
    except Exception:  # noqa: BLE001
        pass


def pytest_unconfigure(config):
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_status["code"])
