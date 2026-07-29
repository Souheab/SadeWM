import os
import sys
import types
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

# Some service tests install a deliberately minimal PySide6.QtGui stub at
# collection time. Complete only the names WindowHelper imports when that stub
# is present; a real PySide6 module is left untouched.
_qtgui = sys.modules.get("PySide6.QtGui")
if _qtgui is not None:
    if not hasattr(_qtgui, "QCursor"):
        _qtgui.QCursor = mock.MagicMock()
    if not hasattr(_qtgui, "QGuiApplication"):
        _qtgui.QGuiApplication = mock.MagicMock()

from services.shared.window_helper import WindowHelper  # noqa: E402


class TestWindowHelper(unittest.TestCase):
    def test_focus_keyboard_uses_xlib_and_closes_connection(self):
        target = object()
        fake_display = mock.MagicMock()
        fake_display.create_resource_object.return_value = target

        xlib_module = types.ModuleType("Xlib")
        xlib_module.X = types.SimpleNamespace(
            RevertToParent=2,
            CurrentTime=0,
        )
        xlib_module.display = types.SimpleNamespace(
            Display=mock.Mock(return_value=fake_display)
        )
        window = mock.MagicMock()
        window.winId.return_value = 123

        with mock.patch.dict(sys.modules, {"Xlib": xlib_module}):
            WindowHelper().focusKeyboard(window)

        fake_display.create_resource_object.assert_called_once_with(
            "window", 123
        )
        fake_display.set_input_focus.assert_called_once_with(target, 2, 0)
        fake_display.sync.assert_called_once_with()
        fake_display.close.assert_called_once_with()

    def test_focus_keyboard_closes_connection_after_x_error(self):
        fake_display = mock.MagicMock()
        fake_display.set_input_focus.side_effect = RuntimeError("BadWindow")

        xlib_module = types.ModuleType("Xlib")
        xlib_module.X = types.SimpleNamespace(
            RevertToParent=2,
            CurrentTime=0,
        )
        xlib_module.display = types.SimpleNamespace(
            Display=mock.Mock(return_value=fake_display)
        )
        window = mock.MagicMock()
        window.winId.return_value = 123

        with mock.patch.dict(sys.modules, {"Xlib": xlib_module}):
            WindowHelper().focusKeyboard(window)

        fake_display.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
