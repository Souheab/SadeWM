import os
import sys
import unittest


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared.window_picker_service import WindowPickerService  # noqa: E402


class TestWindowPickerService(unittest.TestCase):
    def test_stale_results_are_ignored_and_models_are_separate(self):
        service = WindowPickerService()
        service._refresh_generation = 2
        service._minimized_generation = 4

        service._apply_windows(1, [{"name": "stale"}])
        service._apply_windows(2, [{"name": "normal"}])
        service._apply_minimized_windows(4, [{"name": "minimized"}])

        self.assertEqual(service.windows, [{"name": "normal"}])
        self.assertEqual(service.minimizedWindows, [{"name": "minimized"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
