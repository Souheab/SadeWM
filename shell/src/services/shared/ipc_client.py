"""Lightweight IPC client for sadeshell — no PySide6 dependency."""

import os
import socket


def send_ipc_command(command: str) -> str:
    """Send a command to a running sadeshell instance on the current DISPLAY."""
    display = os.environ.get("DISPLAY", ":0")
    display_clean = display.lstrip(":").replace(".", "_").replace("/", "_")
    socket_path = f"/tmp/sadeshell-{display_clean}.sock"

    if not os.path.exists(socket_path):
        return f"error: no sadeshell instance found for DISPLAY={display}"

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(2.0)
        sock.connect(socket_path)
        sock.sendall(command.encode("utf-8") + b"\n")
        response = sock.recv(4096).decode("utf-8").strip()
        return response
    except (ConnectionRefusedError, FileNotFoundError):
        return f"error: could not connect to sadeshell on DISPLAY={display}"
    except socket.timeout:
        return "error: sadeshell did not respond in time"
    finally:
        sock.close()
