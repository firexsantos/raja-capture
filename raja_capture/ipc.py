"""Single-instance support: later launches forward their command to the running app."""

from __future__ import annotations

import getpass
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"raja-capture-{user}"


def send_to_running(command: dict) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(command).encode("utf-8") + b"\n")
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class IpcServer(QObject):
    commandReceived = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        name = _server_name()
        if not self.server.listen(name):
            QLocalServer.removeServer(name)  # stale socket left by a crash
            self.server.listen(name)
        self.server.newConnection.connect(self._on_conn)

    def _on_conn(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._read(s, final=True))
            self._read(sock)  # data may already be buffered before readyRead was connected

    def _read(self, sock, final: bool = False):
        try:
            self._read_lines(sock, final)
            if final:
                sock.deleteLater()
        except RuntimeError:
            pass  # socket already destroyed (e.g. app shutting down)

    def _read_lines(self, sock, final: bool):
        while sock.canReadLine() or (final and sock.bytesAvailable()):
            line = bytes(sock.readLine()).decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(cmd, dict):
                self.commandReceived.emit(cmd)
