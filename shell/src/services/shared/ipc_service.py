"""IPC service — Unix domain socket server for controlling sadeshell."""

import os
import socket
import threading

from PySide6.QtCore import QObject, Signal, Slot, QMetaObject, Qt


class IPCService(QObject):
    """Listens on a Unix domain socket for commands from external tools.

    The socket path is derived from the current DISPLAY env variable so that
    each sadeshell instance (one per X display) gets its own socket.
    """

    openLauncherRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        display = os.environ.get("DISPLAY", ":0")
        display_clean = display.lstrip(":").replace(".", "_").replace("/", "_")
        self._socket_path = f"/tmp/sadeshell-{display_clean}.sock"
        self._server = None
        self._thread = None
        self._running = False

    @property
    def socket_path(self):
        return self._socket_path

    def start(self):
        """Start the IPC server in a background daemon thread."""
        # Remove stale socket
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self._socket_path)
        self._server.listen(5)
        self._server.settimeout(1.0)
        self._running = True

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                conn, _ = self._server.accept()
                try:
                    data = conn.recv(4096).decode("utf-8").strip()
                    self._handle(conn, data)
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    continue
                break

    def _handle(self, conn, data):
        if data == "open-launcher":
            # Emit signal on the main thread via queued invocation
            QMetaObject.invokeMethod(
                self, "_emit_open_launcher", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        else:
            conn.sendall(b"unknown command\n")

    @Slot()
    def _emit_open_launcher(self):
        self.openLauncherRequested.emit()

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        try:
            os.unlink(self._socket_path)
        except (FileNotFoundError, OSError):
            pass
