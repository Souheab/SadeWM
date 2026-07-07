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
        def emit(self):
            pass

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
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = qtcore

from services.shared import keybind_service  # noqa: E402


class TestKeybindService(unittest.TestCase):
    def test_refresh_loads_keybinds(self):
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

        with mock.patch.object(keybind_service, "send_wm_command", return_value=response):
            self.assertTrue(service.refresh())

        self.assertEqual(service.error, "")
        self.assertEqual(service.keybinds, response["keybinds"])

    def test_refresh_reports_error(self):
        service = keybind_service.KeybindService()

        with mock.patch.object(
            keybind_service,
            "send_wm_command",
            return_value={"ok": False, "error": "socket unavailable"},
        ):
            self.assertFalse(service.refresh())

        self.assertEqual(service.error, "socket unavailable")
        self.assertEqual(service.keybinds, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
