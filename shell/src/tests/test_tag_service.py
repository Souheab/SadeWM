import io
import json
import os
import sys
import types
import unittest
from unittest import mock


if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")

    class _Signal:
        def __init__(self, *args):
            self._handlers = []

        def connect(self, handler):
            self._handlers.append(handler)

        def emit(self, *args):
            for handler in list(self._handlers):
                handler(*args)

    class _QObject:
        def __init__(self, parent=None):
            pass

    class _QTimer:
        def __init__(self, parent=None):
            self.interval = 0
            self.timeout = _Signal()

        def setInterval(self, interval):
            self.interval = interval

        def start(self):
            pass

    def _Property(*args, **kwargs):
        def decorator(fn):
            return property(fn)
        return decorator

    def _Slot(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    qtcore.QObject = _QObject
    qtcore.Property = _Property
    qtcore.QTimer = _QTimer
    qtcore.Signal = _Signal
    qtcore.Slot = _Slot
    pyside6.QtCore = qtcore
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.bar import tag_service  # noqa: E402


class _FakeSocket:
    def __init__(self, lines):
        self.lines = lines
        self.sent = b""
        self.connected_to = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, timeout):
        pass

    def connect(self, path):
        self.connected_to = path

    def sendall(self, payload):
        self.sent += payload

    def shutdown(self, how):
        pass

    def makefile(self, mode):
        return io.BytesIO(b"".join(self.lines))


class TestTagService(unittest.TestCase):
    def setUp(self):
        for name in ("tagsChanged", "_pollFinished", "_streamTagsReceived", "_streamStatusChanged"):
            signal = getattr(tag_service.TagService, name, None)
            if hasattr(signal, "_handlers"):
                signal._handlers.clear()

    def test_apply_tags_emits_only_on_change(self):
        svc = tag_service.TagService(start_subscription=False)
        changes = []
        svc.tagsChanged.connect(lambda: changes.append(list(svc.tags)))

        svc._apply_tags(["A", "I"])
        svc._apply_tags(["A", "I"])
        svc._apply_tags(["I", "A"])

        self.assertEqual(changes, [["A", "I"], ["I", "A"]])

    def test_subscription_stream_applies_tag_events(self):
        payload = {
            "event": "tags_state",
            "tag_mask": 2,
            "tags_state": ["I", "A"],
        }
        fake = _FakeSocket([json.dumps(payload).encode() + b"\n"])
        svc = tag_service.TagService(start_subscription=False)

        with mock.patch.object(tag_service.socket, "socket", return_value=fake):
            connected = svc._read_subscription_stream()

        self.assertTrue(connected)
        self.assertEqual(svc.tags, ["I", "A"])
        self.assertEqual(json.loads(fake.sent.decode()), {"cmd": "subscribe_tags"})

    def test_poll_skips_while_stream_connected(self):
        svc = tag_service.TagService(start_subscription=False)
        svc._stream_connected = True

        with mock.patch.object(tag_service.threading, "Thread") as thread_cls:
            svc._poll()

        thread_cls.assert_not_called()

    def test_view_tag_sends_command_in_worker_thread(self):
        svc = tag_service.TagService(start_subscription=False)

        with mock.patch.object(svc, "_send_command_async") as send_async:
            svc.viewTag(3)

        send_async.assert_called_once_with({"cmd": "view", "mask": 4})


if __name__ == "__main__":
    unittest.main(verbosity=2)
