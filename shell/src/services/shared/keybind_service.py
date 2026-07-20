"""QML-facing service for sadewm keybinding help."""

import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, Qt

from .wm_ipc_client import send_wm_command


class KeybindService(QObject):
    keybindsChanged = Signal()
    errorChanged = Signal()
    _responseReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keybinds = []
        self._error = ""
        self._refresh_running = False
        self._refresh_pending = False
        self._responseReady.connect(
            self._apply_response, Qt.ConnectionType.QueuedConnection
        )

    @Property("QVariantList", notify=keybindsChanged)
    def keybinds(self):
        return self._keybinds

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    def _set_error(self, message: str):
        if self._error == message:
            return
        self._error = message
        self.errorChanged.emit()

    @Slot()
    def refresh(self):
        if self._refresh_running:
            self._refresh_pending = True
            return
        self._refresh_running = True

        def _run():
            self._responseReady.emit(send_wm_command("keybinds"))

        threading.Thread(
            target=_run, daemon=True, name="sadeshell-keybinds"
        ).start()

    @Slot(object)
    def _apply_response(self, response):
        self._refresh_running = False
        if response.get("ok") is not True:
            self._keybinds = []
            self.keybindsChanged.emit()
            self._set_error(response.get("error", "sadewm keybind request failed"))
        else:
            keybinds = response.get("keybinds", [])
            if not isinstance(keybinds, list):
                keybinds = []

            self._keybinds = keybinds
            self.keybindsChanged.emit()
            self._set_error("")

        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh()
