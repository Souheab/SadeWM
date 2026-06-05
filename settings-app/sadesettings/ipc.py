"""Lightweight sadewm IPC client."""

from __future__ import annotations

import json
import os
import socket


def get_socket_path() -> str:
    if path := os.environ.get("SADEWM_SOCKET"):
        return path
    display = os.environ.get("DISPLAY", "")
    if not display:
        return "/tmp/sadewm.sock"
    safe = display.lstrip(":").replace(".", "-")
    return f"/tmp/sadewm-{safe}.sock"


def send_reload() -> dict:
    path = get_socket_path()
    payload = json.dumps({"cmd": "reload"}).encode("utf-8")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(2.0)
        sock.connect(path)
        sock.sendall(payload)
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        if not data:
            return {"ok": False, "error": "empty response from sadewm"}
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        sock.close()
