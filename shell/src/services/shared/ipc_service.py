"""IPC service — Unix domain socket server for controlling sadeshell."""

import os
import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

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
    openKeybindsRequested = Signal()
    openEmojiPickerRequested = Signal()
    openWindowPickerRequested = Signal()
    openMinimizedPickerRequested = Signal()
    confirmExitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket_path = _ipc_socket_path()
        self._server = None
        self._thread = None
        self._running = False
        self._owns_socket = False
        self._connections = None

    @property
    def socket_path(self):
        return self._socket_path

    def start(self):
        """Start the IPC server, returning False when another shell owns it."""
        if self._running:
            return True

        if os.path.exists(self._socket_path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.25)
                probe.connect(self._socket_path)
            except (ConnectionRefusedError, FileNotFoundError):
                # Nothing is listening; this is a stale socket from an
                # unclean shutdown and is safe to replace.
                try:
                    os.unlink(self._socket_path)
                except FileNotFoundError:
                    pass
            except OSError:
                # Timeouts and other connection errors can mean a live server
                # with a busy backlog. Do not steal its pathname.
                print(
                    f"sadeshell IPC: socket is already in use: {self._socket_path}",
                    flush=True,
                )
                return False
            else:
                print(
                    f"sadeshell IPC: another shell is already listening on "
                    f"{self._socket_path}",
                    flush=True,
                )
                return False
            finally:
                probe.close()

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server.bind(self._socket_path)
        except OSError:
            self._server.close()
            self._server = None
            raise
        self._server.listen(5)
        self._server.settimeout(0.5)
        self._owns_socket = True
        self._connections = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="sadeshell-ipc"
        )
        self._running = True

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="sadeshell-ipc-accept"
        )
        self._thread.start()
        print(f"sadeshell IPC: listening on {self._socket_path}", flush=True)
        return True

    def _run(self):
        while self._running:
            try:
                conn, _ = self._server.accept()
                executor = self._connections
                if executor is None:
                    conn.close()
                    continue
                try:
                    executor.submit(self._serve_connection, conn)
                except RuntimeError:
                    conn.close()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    continue
                break

    def _serve_connection(self, conn):
        """Read one bounded request without blocking the accept loop."""
        try:
            with conn:
                conn.settimeout(1.0)
                data = conn.recv(4096)
                if not data:
                    return
                self._handle(conn, data.decode("utf-8").strip())
        except (OSError, UnicodeDecodeError):
            pass

    def _handle(self, conn, data):
        if data == "open-launcher":
            QMetaObject.invokeMethod(
                self, "_emit_open_launcher", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        elif data == "open-keybinds":
            QMetaObject.invokeMethod(
                self, "_emit_open_keybinds", Qt.ConnectionType.QueuedConnection
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
        elif data == "open-minimized-picker":
            QMetaObject.invokeMethod(
                self, "_emit_open_minimized_picker", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        elif data == "confirm-exit":
            QMetaObject.invokeMethod(
                self, "_emit_confirm_exit", Qt.ConnectionType.QueuedConnection
            )
            conn.sendall(b"ok\n")
        else:
            conn.sendall(b"unknown command\n")

    @Slot()
    def _emit_open_launcher(self):
        self.openLauncherRequested.emit()

    @Slot()
    def _emit_open_keybinds(self):
        self.openKeybindsRequested.emit()

    @Slot()
    def _emit_open_emoji_picker(self):
        self.openEmojiPickerRequested.emit()

    @Slot()
    def _emit_open_window_picker(self):
        self.openWindowPickerRequested.emit()

    @Slot()
    def _emit_open_minimized_picker(self):
        self.openMinimizedPickerRequested.emit()

    @Slot()
    def _emit_confirm_exit(self):
        self.confirmExitRequested.emit()

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._connections:
            self._connections.shutdown(wait=False, cancel_futures=True)
            self._connections = None
        if self._owns_socket:
            try:
                os.unlink(self._socket_path)
            except (FileNotFoundError, OSError):
                pass
            self._owns_socket = False
