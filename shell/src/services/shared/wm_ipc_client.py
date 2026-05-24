"""Lightweight IPC client for sadewm."""

import json
import os
import socket


def get_socket_path() -> str:
    """Return the sadewm IPC socket path for the current DISPLAY."""
    if p := os.environ.get("SADEWM_SOCKET"):
        return p
    display = os.environ.get("DISPLAY", "")
    if not display:
        return "/tmp/sadewm.sock"
    safe = display.lstrip(":").replace(".", "-")
    return f"/tmp/sadewm-{safe}.sock"


def send_wm_command(command: str, **kwargs) -> dict:
    """Send a JSON IPC command to sadewm and return the decoded response."""
    payload = {"cmd": command, **kwargs}
    path = get_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(2.0)
        sock.connect(path)
        sock.sendall(json.dumps(payload).encode("utf-8"))
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
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def quit_wm() -> bool:
    """Request a clean sadewm exit."""
    return send_wm_command("quit").get("ok") is True
