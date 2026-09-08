import unittest
from unittest import mock

from sadeshell.services.shared import keybind_service  # noqa: E402


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
