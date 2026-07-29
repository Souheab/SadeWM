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

from services.shared import window_helper as window_helper_module  # noqa: E402


WindowHelper = window_helper_module.WindowHelper


class TestWindowHelper(unittest.TestCase):
    def test_active_screen_geometry_returns_values_instead_of_screen_object(self):
        geometry = mock.MagicMock()
        geometry.x.return_value = -1920
        geometry.y.return_value = 0
        geometry.width.return_value = 1920
        geometry.height.return_value = 1080
        screen = mock.MagicMock()
        screen.geometry.return_value = geometry
        cursor_position = object()

        with mock.patch.object(
            window_helper_module.QCursor, "pos", return_value=cursor_position
        ), mock.patch.object(
            window_helper_module.QGuiApplication, "screenAt", return_value=screen
        ) as screen_at:
            result = WindowHelper().activeScreenGeometry()

        screen_at.assert_called_once_with(cursor_position)
        self.assertEqual(
            result,
            {"x": -1920, "y": 0, "width": 1920, "height": 1080},
        )

    def test_active_screen_geometry_falls_back_to_primary_screen(self):
        geometry = mock.MagicMock()
        geometry.x.return_value = 0
        geometry.y.return_value = 0
        geometry.width.return_value = 2560
        geometry.height.return_value = 1440
        primary_screen = mock.MagicMock()
        primary_screen.geometry.return_value = geometry

        with mock.patch.object(
            window_helper_module.QCursor, "pos", return_value=object()
        ), mock.patch.object(
            window_helper_module.QGuiApplication, "screenAt", return_value=None
        ), mock.patch.object(
            window_helper_module.QGuiApplication,
            "primaryScreen",
            return_value=primary_screen,
        ):
            result = WindowHelper().activeScreenGeometry()

        self.assertEqual(
            result,
            {"x": 0, "y": 0, "width": 2560, "height": 1440},
        )

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
