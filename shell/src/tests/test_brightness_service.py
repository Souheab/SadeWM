import os
import sys
import threading
import time
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.bar import brightness_service  # noqa: E402


class TestBrightnessService(unittest.TestCase):
    def test_drag_values_are_coalesced_on_one_worker(self):
        first_started = threading.Event()
        release_first = threading.Event()
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if len(calls) == 1:
                first_started.set()
                release_first.wait(timeout=2)
            return mock.Mock(stdout="")

        with mock.patch.object(
            brightness_service.BrightnessService, "_list_displays"
        ), mock.patch.object(brightness_service.subprocess, "run", side_effect=run):
            service = brightness_service.BrightnessService()
            service.applyBrightness("DP-1", 0.1)
            self.assertTrue(first_started.wait(timeout=1))
            service.applyBrightness("DP-1", 0.2)
            service.applyBrightness("DP-1", 0.3)
            release_first.set()

            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with service._set_lock:
                    if not service._set_running:
                        break
                time.sleep(0.01)

        self.assertEqual(
            [command[-1] for command in calls],
            ["0.100", "0.300"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
