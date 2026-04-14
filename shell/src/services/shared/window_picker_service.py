"""WindowPickerService — exposes all managed windows for the window-picker popup.

Uses:
- sadewm IPC socket to enumerate clients (get_clients) and focus them (focus_window)
- python-xlib (via Xlib) to read _NET_WM_ICON for per-window icons
- xwd + ImageMagick (convert) to capture window thumbnails as base64 PNG data URIs,
  falling back gracefully when unavailable.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer


# ---------------------------------------------------------------------------
# sadewm IPC helpers (same pattern as tag_service.py)
# ---------------------------------------------------------------------------

def _get_sadewm_socket() -> str:
    if p := os.environ.get("SADEWM_SOCKET"):
        return p
    display = os.environ.get("DISPLAY", "")
    if display:
        safe = display.lstrip(":").replace(".", "-")
        return f"/tmp/sadewm-{safe}.sock"
    return "/tmp/sadewm.sock"


def _sadewm_request(request: dict) -> dict:
    path = _get_sadewm_socket()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(path)
            s.sendall(json.dumps(request).encode())
            s.shutdown(socket.SHUT_WR)
            data = b""
            while chunk := s.recv(65536):
                data += chunk
        return json.loads(data)
    except Exception:
        return {"ok": False}


# ---------------------------------------------------------------------------
# Icon resolution helpers via python-xlib
# ---------------------------------------------------------------------------

_xlib_display = None
_xlib_lock = threading.Lock()


def _get_xlib_display():
    global _xlib_display
    with _xlib_lock:
        if _xlib_display is None:
            try:
                from Xlib import display as xdisplay
                _xlib_display = xdisplay.Display()
            except Exception:
                pass
    return _xlib_display


def _net_wm_icon_data_uri(win_id: int) -> str:
    """Read _NET_WM_ICON and return a data: URI for the largest icon, or ''."""
    dpy = _get_xlib_display()
    if dpy is None:
        return ""
    try:
        from Xlib import X
        atom = dpy.intern_atom("_NET_WM_ICON", only_if_exists=True)
        if atom == X.NONE:
            return ""
        win = dpy.create_resource_object("window", win_id)
        prop = win.get_full_property(atom, X.AnyPropertyType)
        if prop is None or not prop.value:
            return ""
        data = list(prop.value)
        # Parse all icons and pick the largest
        best_w, best_h, best_pixels = 0, 0, []
        idx = 0
        while idx + 2 <= len(data):
            w = data[idx]
            h = data[idx + 1]
            idx += 2
            n = w * h
            if idx + n > len(data):
                break
            if w * h > best_w * best_h:
                best_w, best_h = w, h
                best_pixels = data[idx: idx + n]
            idx += n
        if not best_pixels:
            return ""
        # Convert ARGB ints to RGBA bytes PNG
        import struct
        import zlib
        # Build raw RGBA scanlines
        def png_bytes(w: int, h: int, argb_pixels: list[int]) -> bytes:
            """Minimal PNG encoder for RGBA data."""
            raw_rows = []
            for row in range(h):
                row_bytes = b"\x00"  # filter type None
                for col in range(w):
                    argb = argb_pixels[row * w + col]
                    a = (argb >> 24) & 0xFF
                    r = (argb >> 16) & 0xFF
                    g = (argb >> 8) & 0xFF
                    b_ = argb & 0xFF
                    row_bytes += struct.pack("BBBB", r, g, b_, a)
                raw_rows.append(row_bytes)
            raw = b"".join(raw_rows)
            compressed = zlib.compress(raw)

            def chunk(tag, data):
                c = tag + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

            ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2 | 4, 0, 0, 0)  # RGBA
            # Correct IHDR: bit_depth=8, color_type=6 (RGBA), compression=0, filter=0, interlace=0
            ihdr_data = struct.pack(">II", w, h) + bytes([8, 6, 0, 0, 0])
            png = b"\x89PNG\r\n\x1a\n"
            png += chunk(b"IHDR", ihdr_data)
            png += chunk(b"IDAT", compressed)
            png += chunk(b"IEND", b"")
            return png

        png = png_bytes(best_w, best_h, best_pixels)
        b64 = base64.b64encode(png).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Window screenshot helpers
# ---------------------------------------------------------------------------

_HAS_XWD = shutil.which("xwd") is not None
_HAS_CONVERT = shutil.which("convert") is not None


def _capture_window_thumbnail(win_id: int, max_size: int = 280) -> str:
    """Capture a window thumbnail as a base64 encoded PNG data URI.

    Uses xwd (X11 window dump) piped through ImageMagick convert for resizing.
    Returns '' on failure.
    """
    if not (_HAS_XWD and _HAS_CONVERT):
        return ""
    display = os.environ.get("DISPLAY", ":0")
    try:
        xwd_proc = subprocess.Popen(
            ["xwd", "-id", str(win_id), "-display", display, "-silent"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        convert_proc = subprocess.Popen(
            [
                "convert",
                "-",           # read from stdin (xwd format)
                "-resize", f"{max_size}x{max_size}>",
                "-format", "png",
                "png:-",       # output PNG to stdout
            ],
            stdin=xwd_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if xwd_proc.stdout:
            xwd_proc.stdout.close()
        png_data, _ = convert_proc.communicate(timeout=3)
        xwd_proc.wait(timeout=1)
        if convert_proc.returncode == 0 and png_data:
            b64 = base64.b64encode(png_data).decode()
            return f"data:image/png;base64,{b64}"
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# WindowPickerService
# ---------------------------------------------------------------------------

class WindowPickerService(QObject):
    """Provides the list of all WM windows with icons & thumbnails.

    windowsChanged is emitted whenever the window list is refreshed.
    Instances are registered as a QML singleton.
    """

    windowsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows: list[dict] = []

    @Property("QVariantList", notify=windowsChanged)
    def windows(self) -> list:
        return self._windows

    @Slot()
    def refresh(self):
        """Re-query all windows from the WM and update the list."""
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        resp = _sadewm_request({"cmd": "get_clients"})
        if not resp.get("ok"):
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_set_windows_empty", Qt.ConnectionType.QueuedConnection)
            return

        clients = resp.get("clients", [])
        result = []
        for c in clients:
            win_id = c.get("win_id", 0)
            name = c.get("name", "")
            wm_class = c.get("class", "")
            tags = c.get("tags", 0)
            # Derive tag number from bitmask (lowest bit set)
            tag_num = 0
            if tags:
                bit = tags & (-tags)  # lowest set bit
                tag_num = bit.bit_length()

            icon_uri = _net_wm_icon_data_uri(win_id)
            # thumbnail is expensive; skip for now — updated lazily via loadThumbnail
            entry = {
                "winId": win_id,
                "name": name,
                "wmClass": wm_class,
                "tags": tags,
                "tagNum": tag_num,
                "focused": c.get("focused", False),
                "minimized": c.get("minimized", False),
                "iconUri": icon_uri,
                "thumbnailUri": "",
            }
            result.append(entry)

        from PySide6.QtCore import QMetaObject, Qt
        self._windows = result
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _emit_changed(self):
        self.windowsChanged.emit()

    @Slot()
    def _set_windows_empty(self):
        self._windows = []
        self.windowsChanged.emit()

    @Slot(int)
    def loadThumbnail(self, win_id: int):
        """Asynchronously capture and inject a thumbnail for a single window."""
        threading.Thread(
            target=self._load_thumb_async, args=(win_id,), daemon=True
        ).start()

    def _load_thumb_async(self, win_id: int):
        uri = _capture_window_thumbnail(win_id)
        from PySide6.QtCore import QMetaObject, Qt
        # Find and update the entry
        for entry in self._windows:
            if entry["winId"] == win_id:
                entry["thumbnailUri"] = uri
                break
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

    @Slot(int)
    def focusWindow(self, win_id: int):
        """Tell the WM to switch to the tag containing win_id and focus it."""
        _sadewm_request({"cmd": "focus_window", "win_id": win_id})
