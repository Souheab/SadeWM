import asyncio
from concurrent.futures import Future
import threading
import time
from unittest import mock

import pytest
from PySide6.QtCore import QCoreApplication

from sadeshell.services.bar.notification_service import NotificationService
from sadeshell.services.bar.wifi_service import network_rows, AP, WIRELESS
from sadeshell.services.bar.fullscreen_service import intersects
from sadeshell.services.shared.async_bus import AsyncService, BusWorker
from sadeshell.services.shared.icon_index import IconIndex
from sadeshell.services.shared.thumbnail_capture import decode_pixels, thumbnail_size
from sadeshell.services.shared import window_picker_service as picker


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    assert predicate()


@pytest.fixture
def notifications():
    with mock.patch.object(NotificationService, "_start_server"):
        service = NotificationService()
    yield service
    service.stop()


def add(service, timeout=5000, replacement=0):
    return service._add_notification("tests", "title", "body", "", timeout, replacement)


def test_notification_replacement_and_exactly_once_close(notifications):
    closed = []
    notifications.notificationClosed.connect(lambda ident, reason: closed.append((ident, reason)))
    ident = add(notifications)
    assert add(notifications, 0, ident) == ident
    assert len(notifications.notifications) == 1
    assert notifications.notifications[0]["expireTimeout"] == 0
    notifications._close(ident, 3)
    notifications._close(ident, 3)
    assert closed == [(ident, 3)]
    assert not notifications.notifications


def test_notification_expiry_starts_when_shown_and_hover_preserves_remaining(notifications):
    ident = add(notifications, 30)
    state = notifications._active[ident]
    assert not state["timer"].isActive()
    notifications.toastShown(ident)
    notifications.setPaused(ident, True)
    time.sleep(0.05)
    QCoreApplication.processEvents()
    assert ident in notifications._active
    notifications.setPaused(ident, False)
    wait_for(lambda: ident not in notifications._active)
    assert notifications.notifications[0]["id"] == ident
    notifications.dismiss(0)
    assert notifications.notifications == []


def test_notification_limits_and_timeout_defaults(notifications):
    assert notifications._active[add(notifications, -1)]["remaining"] == 5000
    closed = []
    notifications.notificationClosed.connect(lambda ident, reason: closed.append(reason))
    for _ in range(205):
        add(notifications, 0)
    assert len(notifications.notifications) == len(notifications._active) == 200
    assert notifications.popupModel.rowCount() == 5
    assert closed == [4] * 6
    for ident in list(notifications._active):
        notifications.toastShown(ident)
        assert not notifications._active[ident]["timer"].isActive()


def test_notification_stop_cancels_deferred_expiry_work():
    import gc
    from PySide6.QtCore import QEvent
    with mock.patch.object(NotificationService, "_start_server"):
        service = NotificationService()
    ident = add(service, 1)
    service.toastShown(ident)
    wait_for(lambda: ident not in service._active)
    assert service._popup_sync_timer.isActive()
    service.stop()
    assert not service._popup_sync_timer.isActive()
    service.deleteLater()
    service = None
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def test_ssid_deduplication_prefers_connected_then_strongest():
    def ap(strength):
        return {AP: dict(Ssid=list(b"same"), Strength=strength, Flags=1)}
    objects = {"/device": {WIRELESS: {"ActiveAccessPoint": "/weak"}}, "/weak": ap(20), "/strong": ap(90)}
    assert network_rows(objects) == [dict(ssid="same", signal=20, secure=True, active=True)]
    objects["/device"][WIRELESS]["ActiveAccessPoint"] = "/"
    assert network_rows(objects)[0]["signal"] == 90


def test_negative_monitor_geometry_and_pixel_formats():
    assert intersects((-1920, 0, 1920, 1080), (-1920, 0, 1920, 1080))
    assert not intersects((-3840, 0, 1920, 1080), (-1920, 0, 1920, 1080))
    assert thumbnail_size(3840, 2160) == (212, 119)
    for data, bpp, order, masks in [
        (bytes([0, 0, 255, 0]), 32, 0, (0xff0000, 0xff00, 0xff)),
        (bytes([0, 255, 0, 0]), 32, 1, (0xff0000, 0xff00, 0xff)),
        (bytes([0, 248, 0, 0]), 16, 0, (0xf800, 0x7e0, 0x1f)),
    ]:
        assert decode_pixels(data, 1, 1, bpp, 32, order, masks).getpixel((0, 0)) == (255, 0, 0)


def test_icon_index_precedence_and_invalidation(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    user.mkdir()
    system.mkdir()
    (user / "demo.png").touch()
    (system / "demo.svg").touch()
    index = IconIndex()
    with mock.patch.object(index, "roots", return_value=[str(user), str(system)]):
        assert index.resolve("demo") == str(user / "demo.png")
        assert index.resolve("missing") == ""
        (user / "missing.svg").touch()
        assert index.resolve("missing") == ""
        index.invalidate()
        assert index.resolve("missing") == str(user / "missing.svg")


def test_private_image_files_are_bounded(tmp_path, monkeypatch):
    from PIL import Image
    from collections import OrderedDict
    monkeypatch.setattr(picker, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(picker, "_CACHE_CLOSED", False)
    monkeypatch.setattr(picker, "_OWNED_FILES", OrderedDict())
    image = Image.new("RGB", (10, 10))
    for index in range(150):
        picker._save_cached_png(image, f"{index}.png")
    assert len(list(tmp_path.iterdir())) == 128
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= 32 * 1024 * 1024


def test_async_results_are_queued_and_device_commands_serialized():
    worker = BusWorker()
    class Service(AsyncService):
        def apply_state(self, state):
            self.state = state
            self.receiver_thread = threading.get_ident()
    service = Service(worker=worker)
    order = []
    async def operation(number):
        order.append(("start", number))
        await asyncio.sleep(0.02)
        service.publish(state=number)
        order.append(("end", number))
    try:
        service.command(operation(1), "device")
        service.command(operation(2), "device")
        wait_for(lambda: not service.busy)
        assert order == [("start", 1), ("end", 1), ("start", 2), ("end", 2)]
        assert service.state == 2
        assert service.receiver_thread == threading.get_ident()
        service.stop()
        service.stop()
    finally:
        worker.stop()


def test_private_image_byte_limit_evicts_oldest(tmp_path, monkeypatch):
    from PIL import Image
    from collections import OrderedDict
    monkeypatch.setattr(picker, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(picker, "_CACHE_CLOSED", False)
    monkeypatch.setattr(picker, "_OWNED_FILES", OrderedDict())
    # Exercise byte accounting without allocating 34 MiB in the test process.
    monkeypatch.setattr(picker.os.path, "getsize", lambda path: 17 * 1024 * 1024)
    image = Image.new("RGB", (1, 1))
    first = picker._save_cached_png(image, "first.png")
    second = picker._save_cached_png(image, "second.png")
    assert not (tmp_path / "first.png").exists()
    assert (tmp_path / "second.png").exists()
    assert list(picker._OWNED_FILES) == [second]
    assert first not in picker._OWNED_FILES


def test_picker_viewport_scheduling_is_bounded_and_close_cancels_pending():
    with mock.patch.object(picker, "ThreadPoolExecutor"), mock.patch.object(picker, "_cleanup_cache"):
        service = picker.WindowPickerService()
        service._windows = [dict(winId=index, name=str(index)) for index in range(50)]
        service._asset_cache = {index: picker._WindowAssets(wm_class="Test") for index in range(50)}
        try:
            service.setRequestedWindows("normal", list(range(10)), True)
            assert len(service._inflight) == 2
            assert len(service._pending) == 8
            for _ in range(10):
                service.setRequestedWindows("normal", list(range(10, 20)), True)
            assert len(service._inflight) == 2
            assert set(service._pending) == set(range(10, 20))
            service.setRequestedWindows("normal", [], False)
            assert not service._pending
        finally:
            service.stop()


def test_media_metadata_changes_notify_all_players():
    from sadeshell.services.bar.media_service import MediaService
    class Worker:
        def __init__(self):
            self.loop = mock.Mock()
        def submit(self, coroutine):
            coroutine.close()
            result = Future()
            result.set_result(None)
            return result
    service = MediaService(worker=Worker())
    changes = []
    service.allPlayersChanged.connect(lambda: changes.append(service.allPlayers))
    row = dict(name="player", owner=":1.1", title="first", artist="", isPlaying=False, position=0, length=10)
    service.apply_state([row])
    service.apply_state([dict(row, title="second")])
    assert changes[-1][0]["title"] == "second"
    assert service.title == "second"
    service.stop()
