"""QML-facing service for sadewm keybinding help."""

from PySide6.QtCore import QObject, Property, Signal, Slot

from .wm_ipc_client import send_wm_command


class KeybindService(QObject):
    keybindsChanged = Signal()
    errorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keybinds = []
        self._error = ""

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

    @Slot(result=bool)
    def refresh(self):
        response = send_wm_command("keybinds")
        if response.get("ok") is not True:
            self._keybinds = []
            self.keybindsChanged.emit()
            self._set_error(response.get("error", "sadewm keybind request failed"))
            return False

        keybinds = response.get("keybinds", [])
        if not isinstance(keybinds, list):
            keybinds = []

        self._keybinds = keybinds
        self.keybindsChanged.emit()
        self._set_error("")
        return True
