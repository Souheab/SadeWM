import os
import stat
import sys
import tempfile
import unittest


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared.window_picker_service import (  # noqa: E402
    WindowPickerService,
    _create_private_cache_dir,
    _remove_private_cache_dir,
    _write_private_png,
)


class _FakeImage:
    def save(self, output, image_format):
        if image_format != "PNG":
            raise AssertionError(f"unexpected image format: {image_format}")
        output.write(b"private image")


class TestWindowPickerService(unittest.TestCase):
    def test_cache_directory_and_images_are_private(self):
        with tempfile.TemporaryDirectory() as parent:
            cache_dir = _create_private_cache_dir(parent)
            self.assertEqual(stat.S_IMODE(os.stat(cache_dir).st_mode), 0o700)

            image_path = _write_private_png(
                _FakeImage(), cache_dir, "thumbnail.png"
            )
            self.assertEqual(stat.S_IMODE(os.stat(image_path).st_mode), 0o600)
            with open(image_path, "rb") as saved:
                self.assertEqual(saved.read(), b"private image")

            _remove_private_cache_dir(cache_dir)
            self.assertFalse(os.path.exists(cache_dir))

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
