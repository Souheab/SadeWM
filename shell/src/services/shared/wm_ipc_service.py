"""QML-facing service for sadewm IPC commands."""

import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, Qt

from .wm_ipc_client import send_wm_command


class WMIPCService(QObject):
    errorChanged = Signal()
    quitFinished = Signal(bool)
    _quitResponseReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._error = ""
        self._quit_running = False
        self._quitResponseReady.connect(
            self._apply_quit_response, Qt.ConnectionType.QueuedConnection
        )

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    def _set_error(self, message: str):
        if self._error == message:
            return
        self._error = message
        self.errorChanged.emit()

    @Slot()
    def quit(self):
        if self._quit_running:
            return
        self._quit_running = True

        def _run():
            self._quitResponseReady.emit(send_wm_command("quit"))

        threading.Thread(
            target=_run, daemon=True, name="sadeshell-wm-quit"
        ).start()

    @Slot(object)
    def _apply_quit_response(self, response):
        self._quit_running = False
        ok = response.get("ok") is True
        self._set_error("" if ok else response.get("error", "sadewm quit request failed"))
        self.quitFinished.emit(ok)
