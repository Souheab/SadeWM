import os
import sys
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared import wm_ipc_service  # noqa: E402


class TestWMIPCService(unittest.TestCase):
    def test_quit_uses_a_background_worker(self):
        service = wm_ipc_service.WMIPCService()
        with mock.patch.object(wm_ipc_service.threading, "Thread") as thread_cls:
            service.quit()

        thread_cls.assert_called_once()
        thread_cls.return_value.start.assert_called_once_with()
        self.assertTrue(service._quit_running)

    def test_quit_response_is_applied_on_service(self):
        service = wm_ipc_service.WMIPCService()
        results = []
        service.quitFinished.connect(results.append)
        service._quit_running = True
        service._apply_quit_response({"ok": False, "error": "offline"})

        self.assertFalse(service._quit_running)
        self.assertEqual(service.error, "offline")
        self.assertEqual(results, [False])


if __name__ == "__main__":
    unittest.main(verbosity=2)
