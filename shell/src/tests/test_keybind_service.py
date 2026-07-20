import os
import sys
import types
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

try:
    import PySide6  # noqa: F401
except ModuleNotFoundError:
    pyside = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")

    class QObject:
        def __init__(self, parent=None):
            self.parent = parent

    class Signal:
        def __init__(self, *args):
            self._slots = []

        def connect(self, slot, _connection=None):
            self._slots.append(slot)

        def emit(self, *args):
            for slot in self._slots:
                slot(*args)

    class Qt:
        class ConnectionType:
            QueuedConnection = None

    def Property(_type, notify=None):
        def decorate(fn):
            return property(fn)

        return decorate

    def Slot(*args, **kwargs):
        def decorate(fn):
            return fn

        return decorate

    qtcore.QObject = QObject
    qtcore.Property = Property
    qtcore.Signal = Signal
    qtcore.Slot = Slot
    qtcore.Qt = Qt
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = qtcore

from services.shared import keybind_service  # noqa: E402


class TestKeybindService(unittest.TestCase):
    def test_response_loads_keybinds(self):
        service = keybind_service.KeybindService()
        response = {
            "ok": True,
            "keybinds": [
                {
                    "mod": ["Super"],
                    "key": "S",
                    "action": "spawn",
                    "description": "Show keybinds",
                }
            ],
        }

        service._refresh_running = True
        service._apply_response(response)

        self.assertEqual(service.error, "")
        self.assertEqual(service.keybinds, response["keybinds"])
        self.assertFalse(service._refresh_running)

    def test_response_reports_error(self):
        service = keybind_service.KeybindService()
        service._refresh_running = True
        service._apply_response({"ok": False, "error": "socket unavailable"})

        self.assertEqual(service.error, "socket unavailable")
        self.assertEqual(service.keybinds, [])
        self.assertFalse(service._refresh_running)

    def test_refresh_runs_ipc_in_background(self):
        service = keybind_service.KeybindService()
        response = {"ok": True, "keybinds": []}

        with (
            mock.patch.object(keybind_service, "send_wm_command", return_value=response),
            mock.patch.object(keybind_service.threading, "Thread") as thread_cls,
        ):
            service.refresh()

        thread_cls.assert_called_once()
        thread_cls.return_value.start.assert_called_once_with()
        self.assertTrue(service._refresh_running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
