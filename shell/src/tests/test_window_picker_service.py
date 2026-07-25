import os
import stat
import sys
import tempfile
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared.window_picker_service import (  # noqa: E402
    WindowPickerService,
    WindowListModel,
    _WindowAssets,
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

    def test_list_model_filters_and_updates_one_window(self):
        model = WindowListModel()
        model.set_items([
            {
                "winId": 1,
                "name": "Terminal",
                "wmClass": "WezTerm",
                "iconUri": "",
            },
            {
                "winId": 2,
                "name": "Documentation",
                "wmClass": "Firefox",
                "iconUri": "",
            },
        ])

        self.assertEqual(model.count, 2)
        model.setFilter("fire")
        self.assertEqual(model.count, 1)
        self.assertEqual(model.get(0)["winId"], 2)

        model.update_item(2, {"iconUri": "file:///icon.png"})
        self.assertEqual(model.get(0)["iconUri"], "file:///icon.png")

    def test_cached_assets_are_reused_in_metadata(self):
        service = WindowPickerService()
        service._asset_cache[7] = _WindowAssets(
            wm_class="Firefox",
            icon_uri="file:///icon.png",
            icon_attempted=True,
            thumbnail_uri="file:///thumb.png",
            thumbnail_attempted_at=1.0,
        )

        entry = service._entry_from_client({
            "win_id": 7,
            "name": "Browser",
            "class": "Firefox",
            "tags": 1,
        })

        self.assertEqual(entry["iconUri"], "file:///icon.png")
        self.assertEqual(entry["thumbnailUri"], "file:///thumb.png")

    def test_entry_formats_all_workspace_tags(self):
        service = WindowPickerService()
        entry = service._entry_from_client({
            "win_id": 8,
            "name": "Editor",
            "class": "Code",
            "tags": (1 << 0) | (1 << 2) | (1 << 4),
        })

        self.assertEqual(entry["tagNum"], 1)
        self.assertEqual(entry["workspaceLabel"], "1, 3, 5")

    def test_recent_focus_order_keeps_previous_window_next(self):
        service = WindowPickerService()
        clients = [
            {"win_id": 1, "focused": True},
            {"win_id": 2, "focused": False},
            {"win_id": 3, "focused": False},
        ]

        first = service._order_by_recent_focus(clients)
        self.assertEqual([client["win_id"] for client in first], [1, 2, 3])

        service._remember_focused_window(3)
        second = service._order_by_recent_focus(clients)
        self.assertEqual([client["win_id"] for client in second], [1, 3, 2])

        clients[0]["focused"] = False
        clients[2]["focused"] = True
        third = service._order_by_recent_focus(clients)
        self.assertEqual([client["win_id"] for client in third], [3, 1, 2])

    def test_normal_refresh_excludes_minimized_windows(self):
        service = WindowPickerService()
        service._refresh_generation = 1
        emitted = []
        service._windowsReady.connect(
            lambda generation, windows: emitted.append((generation, windows))
        )
        responses = [
            {"ok": True, "tag_mask": 1},
            {
                "ok": True,
                "clients": [
                    {
                        "win_id": 1,
                        "name": "Visible",
                        "class": "Terminal",
                        "tags": 1,
                        "focused": True,
                        "minimized": False,
                    },
                    {
                        "win_id": 2,
                        "name": "Hidden",
                        "class": "Browser",
                        "tags": 1,
                        "focused": False,
                        "minimized": True,
                    },
                ],
            },
        ]

        with mock.patch(
            "services.shared.window_picker_service._sadewm_request",
            side_effect=responses,
        ), mock.patch.object(service, "_capture_assets"):
            service._do_refresh(1)

        self.assertEqual(len(emitted), 1)
        self.assertEqual(
            [entry["winId"] for entry in emitted[0][1]],
            [1],
        )

    def test_capture_cache_prevents_immediate_recapture(self):
        service = WindowPickerService()
        entry = service._entry_from_client({
            "win_id": 9,
            "name": "Terminal",
            "class": "WezTerm",
            "tags": 1,
            "focused": True,
        })

        calls = []

        def fake_capture(kind, captured_entry):
            calls.append((kind, captured_entry["winId"]))
            return f"file:///{kind}.png"

        with mock.patch.object(
            service, "_capture_asset", side_effect=fake_capture
        ):
            service._capture_assets(
                1,
                "normal",
                [entry],
                current_tags=1,
                include_thumbnails=True,
            )
            service._capture_assets(
                1,
                "normal",
                [entry],
                current_tags=1,
                include_thumbnails=True,
            )

        self.assertCountEqual(calls, [("thumbnail", 9), ("icon", 9)])

    def test_failed_refresh_keeps_last_good_thumbnail(self):
        service = WindowPickerService()
        service._asset_cache[11] = _WindowAssets(
            wm_class="Editor",
            icon_attempted=True,
            thumbnail_uri="file:///last-good.png",
            thumbnail_attempted_at=0.0,
            thumbnail_geometry=(800, 600),
        )
        entry = service._entry_from_client({
            "win_id": 11,
            "name": "Editor",
            "class": "Editor",
            "tags": 1,
            "width": 800,
            "height": 600,
        })

        with mock.patch.object(service, "_capture_asset", return_value=""):
            service._capture_assets(
                1,
                "normal",
                [entry],
                current_tags=1,
                include_thumbnails=True,
            )

        self.assertEqual(
            service._asset_cache[11].thumbnail_uri,
            "file:///last-good.png",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
