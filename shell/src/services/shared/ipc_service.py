"""IPC service — Unix domain socket server for controlling sadeshell."""

import os
import re
import socket
import threading

from PySide6.QtCore import QObject, Signal, Slot, QMetaObject, Qt


def _ipc_socket_path() -> str:
    """Compute the IPC socket path for the current session.

    Uses XDG_RUNTIME_DIR (always set in systemd user sessions) as the primary
    directory.  Falls back to /tmp if XDG_RUNTIME_DIR is not available.
    DISPLAY is normalised so that ':0' and ':0.0' map to the same socket.
    """
    display = os.environ.get("DISPLAY", ":0")
    # Normalise: strip screen number (:0.0 → :0)
    display = re.sub(r"\.\d+$", "", display)
    display_clean = display.lstrip(":").replace("/", "_") or "0"
    filename = f"sadeshell-{display_clean}.sock"
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, filename)
    return os.path.join("/tmp", filename)


class IPCService(QObject):
    """Listens on a Unix domain socket for commands from external tools.

    The socket path is derived from XDG_RUNTIME_DIR (preferred) or /tmp,
    keyed on the normalised X11 DISPLAY value.
    """

    openLauncherRequested = Signal()
    openEmojiPickerRequested = Signal()
    openWindowPickerRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket_path = _ipc_socket_path()
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
        print(f"sadeshell IPC: listening on {self._socket_path}", flush=True)

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
            QMetaObject.invokeMethod(
                self, "_emit_open_launcher", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        elif data == "open-emoji-picker":
            QMetaObject.invokeMethod(
                self, "_emit_open_emoji_picker", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        elif data == "open-window-picker":
            QMetaObject.invokeMethod(
                self, "_emit_open_window_picker", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        else:
            conn.sendall(b"unknown command\n")

    @Slot()
    def _emit_open_launcher(self):
        self.openLauncherRequested.emit()

    @Slot()
    def _emit_open_emoji_picker(self):
        self.openEmojiPickerRequested.emit()

    @Slot()
    def _emit_open_window_picker(self):
        self.openWindowPickerRequested.emit()

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
