"""QML-facing service for sadewm IPC commands."""

from PySide6.QtCore import QObject, Property, Signal, Slot

from .wm_ipc_client import send_wm_command


class WMIPCService(QObject):
    errorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._error = ""

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    def _set_error(self, message: str):
        if self._error == message:
            return
        self._error = message
        self.errorChanged.emit()

    @Slot(result=bool)
    def quit(self):
        response = send_wm_command("quit")
        ok = response.get("ok") is True
        self._set_error("" if ok else response.get("error", "sadewm quit request failed"))
        return ok
