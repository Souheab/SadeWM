"""TagService — monitors dwm/sadewm workspace tag state via Unix socket."""

import json
import socket
import os
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer


def _get_socket_path() -> str:
    """Return the sadewm IPC socket path for the current DISPLAY.

    Priority:
    1. SADEWM_SOCKET env var (explicit override)
    2. Derived from DISPLAY: DISPLAY=:0  → /tmp/sadewm-0.sock
                             DISPLAY=:1  → /tmp/sadewm-1.sock
    3. Fallback: /tmp/sadewm.sock
    """
    if p := os.environ.get("SADEWM_SOCKET"):
        return p
    display = os.environ.get("DISPLAY", "")
    if display:
        safe = display.lstrip(":").replace(".", "-")
        return f"/tmp/sadewm-{safe}.sock"
    return "/tmp/sadewm.sock"


SOCKET_PATH = _get_socket_path()


def _sadewm_request(request: dict) -> dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(json.dumps(request).encode())
            s.shutdown(socket.SHUT_WR)
            data = b""
            while chunk := s.recv(4096):
                data += chunk
        return json.loads(data)
    except Exception:
        return {"ok": False}


class TagService(QObject):
    tagsChanged = Signal()
    _pollFinished = Signal("QVariantList")
    _streamTagsReceived = Signal("QVariantList")
    _streamStatusChanged = Signal(bool)

    def __init__(self, parent=None, start_subscription=True):
        super().__init__(parent)
        self._tags = []
        self._poll_inflight = False
        self._stream_connected = False
        self._poll_lock = threading.Lock()
        self._pollFinished.connect(self._apply_poll_result)
        self._streamTagsReceived.connect(self._apply_tags)
        self._streamStatusChanged.connect(self._set_stream_connected)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        if start_subscription:
            threading.Thread(target=self._subscription_worker, daemon=True).start()

    def _poll(self):
        if self._stream_connected:
            return
        with self._poll_lock:
            if self._poll_inflight:
                return
            self._poll_inflight = True

        threading.Thread(target=self._poll_worker, daemon=True).start()

    def _poll_worker(self):
        res = _sadewm_request({"cmd": "tags_state"})
        if res.get("ok"):
            self._pollFinished.emit(res.get("tags_state", []))
        else:
            with self._poll_lock:
                self._poll_inflight = False

    @Slot("QVariantList")
    def _apply_poll_result(self, new_tags):
        with self._poll_lock:
            self._poll_inflight = False
        self._apply_tags(new_tags)

    @Slot("QVariantList")
    def _apply_tags(self, new_tags):
        if new_tags != self._tags:
            self._tags = new_tags
            self.tagsChanged.emit()

    @Slot(bool)
    def _set_stream_connected(self, connected: bool):
        self._stream_connected = connected

    def _subscription_worker(self):
        backoff = 0.25
        while True:
            connected = False
            try:
                connected = self._read_subscription_stream()
                backoff = 0.25
            except Exception:
                pass
            finally:
                if connected:
                    self._streamStatusChanged.emit(False)

            time.sleep(backoff)
            backoff = min(backoff * 2, 2.0)

    def _read_subscription_stream(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            s.sendall(json.dumps({"cmd": "subscribe_tags"}).encode())
            s.shutdown(socket.SHUT_WR)
            s.settimeout(None)
            self._streamStatusChanged.emit(True)

            with s.makefile("rb") as stream:
                for raw_line in stream:
                    try:
                        event = json.loads(raw_line.decode())
                    except Exception:
                        continue
                    if event.get("event") == "tags_state":
                        self._streamTagsReceived.emit(event.get("tags_state", []))
            return True

    @Property("QVariantList", notify=tagsChanged)
    def tags(self):
        return self._tags

    @Slot(int)
    def viewTag(self, tag_num: int):
        mask = 1 << (tag_num - 1)
        self._send_command_async({"cmd": "view", "mask": mask})

    @Slot(int)
    def toggleViewTag(self, tag_num: int):
        mask = 1 << (tag_num - 1)
        self._send_command_async({"cmd": "toggleview", "mask": mask})

    def _send_command_async(self, request: dict):
        threading.Thread(target=_sadewm_request, args=(request,), daemon=True).start()
