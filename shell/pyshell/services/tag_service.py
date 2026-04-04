"""TagService — monitors dwm/sadewm workspace tag state via Unix socket."""

import json
import socket
import os

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer


SOCKET_PATH = os.environ.get("SADEWM_SOCKET", "/tmp/sadewm.sock")


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags = []

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _poll(self):
        res = _sadewm_request({"cmd": "tags_state"})
        if res.get("ok"):
            new_tags = res.get("tags_state", [])
            if new_tags != self._tags:
                self._tags = new_tags
                self.tagsChanged.emit()

    @Property("QVariantList", notify=tagsChanged)
    def tags(self):
        return self._tags

    @Slot(int)
    def viewTag(self, tag_num: int):
        mask = 1 << (tag_num - 1)
        _sadewm_request({"cmd": "view", "mask": mask})

    @Slot(int)
    def toggleViewTag(self, tag_num: int):
        mask = 1 << (tag_num - 1)
        _sadewm_request({"cmd": "toggleview", "mask": mask})
