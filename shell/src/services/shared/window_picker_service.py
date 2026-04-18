"""WindowPickerService — exposes all managed windows for the window-picker popup.

Uses:
- sadewm IPC socket to enumerate clients (get_clients) and focus them (focus_window)
- python-xlib to read _NET_WM_ICON for per-window icons, with XDG theme fallback
- python-xlib get_image() + Pillow for window thumbnails (no external tools needed)
- Images are saved to /tmp/sadeshell-winpicker/ as PNG files and exposed as file:// URIs
"""

from __future__ import annotations

import glob
import io
import json
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Property, Signal, Slot

# Cache dir for saved thumbnails and icons
_CACHE_DIR = "/tmp/sadeshell-winpicker"
os.makedirs(_CACHE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# sadewm IPC helpers
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
# Icon resolution — _NET_WM_ICON then XDG theme fallback
# ---------------------------------------------------------------------------

def _build_icon_search_dirs() -> list[str]:
    """Return icon search directories from XDG_DATA_DIRS + nix paths."""
    dirs: list[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            dirs.append(p)

    home = os.path.expanduser("~")
    add(os.path.join(home, ".local/share/icons"))
    add(os.path.join(home, ".local/share/pixmaps"))

    for base in os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share").split(":"):
        add(os.path.join(base, "icons"))
        add(os.path.join(base, "pixmaps"))

    # NixOS: nix profile and current system
    for nix in (
        os.path.join(home, ".nix-profile/share"),
        "/run/current-system/sw/share",
    ):
        add(os.path.join(nix, "icons"))
        add(os.path.join(nix, "pixmaps"))

    return dirs


_ICON_DIRS: list[str] | None = None
_ICON_DIRS_LOCK = threading.Lock()


def _icon_search_dirs() -> list[str]:
    global _ICON_DIRS
    with _ICON_DIRS_LOCK:
        if _ICON_DIRS is None:
            _ICON_DIRS = _build_icon_search_dirs()
    return _ICON_DIRS


def _icon_path_from_class(wm_class: str) -> str:
    """Look up <wm_class> in XDG icon theme dirs. Returns file path or ''."""
    if not wm_class:
        return ""
    names = [wm_class, wm_class.lower()]
    for d in _icon_search_dirs():
        for name in names:
            for ext in ("png", "svg", "xpm"):
                # Prefer 48x48/apps, then any apps dir, then any match
                for pattern in (
                    f"{d}/**/48x48/apps/{name}.{ext}",
                    f"{d}/**/32x32/apps/{name}.{ext}",
                    f"{d}/**/apps/{name}.{ext}",
                    f"{d}/**/{name}.{ext}",
                    f"{d}/{name}.{ext}",
                ):
                    matches = glob.glob(pattern, recursive=True)
                    if matches:
                        return matches[0]
    return ""


def _net_wm_icon_file_uri(win_id: int, wm_class: str) -> str:
    """Return a file:// URI for the window icon.

    Tries in order:
    1. _NET_WM_ICON X property (ARGB pixels) — saved as PNG to cache dir
    2. WM_CLASS-based XDG icon theme lookup
    Returns '' if nothing found.
    """
    try:
        from PIL import Image
        from Xlib import display as xdisplay, X

        # Fresh connection per call — python-xlib is not thread-safe
        dpy = xdisplay.Display()
        atom = dpy.intern_atom("_NET_WM_ICON", only_if_exists=True)

        if atom != X.NONE:
            win = dpy.create_resource_object("window", win_id)
            prop = win.get_full_property(atom, X.AnyPropertyType)
            if prop is not None and prop.value:
                values = list(prop.value)
                best_w = best_h = best_start = 0
                idx = 0
                while idx + 2 <= len(values):
                    w_icon = int(values[idx])
                    h_icon = int(values[idx + 1])
                    idx += 2
                    n = w_icon * h_icon
                    if idx + n > len(values):
                        break
                    if w_icon * h_icon > best_w * best_h:
                        best_w, best_h = w_icon, h_icon
                        best_start = idx
                    idx += n
                if best_w > 0:
                    # Convert ARGB ints → RGBA bytes
                    raw = bytearray(best_w * best_h * 4)
                    for i in range(best_w * best_h):
                        argb = int(values[best_start + i])
                        raw[i * 4]     = (argb >> 16) & 0xFF  # R
                        raw[i * 4 + 1] = (argb >> 8) & 0xFF   # G
                        raw[i * 4 + 2] = argb & 0xFF           # B
                        raw[i * 4 + 3] = (argb >> 24) & 0xFF  # A
                    img = Image.frombytes("RGBA", (best_w, best_h), bytes(raw))
                    out_path = os.path.join(_CACHE_DIR, f"icon_{win_id}.png")
                    img.save(out_path, "PNG")
                    dpy.close()
                    return f"file://{out_path}"
        dpy.close()
    except Exception:
        pass

    # Fallback: XDG theme lookup by WM_CLASS
    path = _icon_path_from_class(wm_class)
    return f"file://{path}" if path else ""


# ---------------------------------------------------------------------------
# Thumbnail capture via python-xlib get_image + Pillow
# ---------------------------------------------------------------------------

_THUMB_W = 280
_THUMB_H = 175


def _capture_thumbnail_file_uri(win_id: int) -> str:
    """Capture a window thumbnail using python-xlib and Pillow.

    Returns a file:// URI pointing to the saved PNG, or '' on failure.
    """
    try:
        from PIL import Image
        from Xlib import display as xdisplay, X

        dpy = xdisplay.Display()
        win = dpy.create_resource_object("window", win_id)

        # Only capture if the window is viewable
        attrs = win.get_attributes()
        if attrs.map_state != X.IsViewable:
            dpy.close()
            return ""

        geom = win.get_geometry()
        w, h = int(geom.width), int(geom.height)
        if w < 1 or h < 1:
            dpy.close()
            return ""

        raw_img = win.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
        dpy.close()

        raw_bytes = bytes(raw_img.data)
        # X11 ZPixmap on little-endian: 32bpp, pixel layout is BGRX
        pil = Image.frombuffer("RGB", (w, h), raw_bytes, "raw", "BGRX", 0, 1)
        pil.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)

        out_path = os.path.join(_CACHE_DIR, f"thumb_{win_id}.png")
        pil.save(out_path, "PNG")
        return f"file://{out_path}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# WindowPickerService
# ---------------------------------------------------------------------------

class WindowPickerService(QObject):
    """Provides the list of all WM windows with icons and thumbnails.

    windowsChanged is emitted whenever the window list is refreshed.
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
        """Re-query all windows from the WM, capture thumbnails and icons."""
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        from PySide6.QtCore import QMetaObject, Qt

        resp = _sadewm_request({"cmd": "get_clients"})
        if not resp.get("ok"):
            self._windows = []
            QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)
            return

        clients = resp.get("clients", [])

        # Phase 1: emit window list immediately with metadata only (no thumbnails/icons)
        result = []
        for c in clients:
            win_id = c.get("win_id", 0)
            wm_class = c.get("class", "")
            tags = c.get("tags", 0)
            tag_num = (tags & -tags).bit_length() if tags else 0
            result.append({
                "winId": win_id,
                "name": c.get("name", ""),
                "wmClass": wm_class,
                "tags": tags,
                "tagNum": tag_num,
                "focused": c.get("focused", False),
                "minimized": c.get("minimized", False),
                "iconUri": "",
                "thumbnailUri": "",
            })

        self._windows = result
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

        # Phase 2: capture thumbnails and icons in parallel, then re-emit
        def _capture(entry):
            win_id = entry["winId"]
            wm_class = entry["wmClass"]
            icon_uri = _net_wm_icon_file_uri(win_id, wm_class)
            thumb_uri = _capture_thumbnail_file_uri(win_id)
            return {**entry, "iconUri": icon_uri, "thumbnailUri": thumb_uri}

        with ThreadPoolExecutor(max_workers=4) as pool:
            enriched = list(pool.map(_capture, result))

        self._windows = enriched
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _emit_changed(self):
        self.windowsChanged.emit()

    @Slot()
    def refreshMinimized(self):
        """Re-query minimized windows on currently selected tags."""
        threading.Thread(target=self._do_refresh_minimized, daemon=True).start()

    def _do_refresh_minimized(self):
        from PySide6.QtCore import QMetaObject, Qt

        # Get current tag mask from WM state
        state_resp = _sadewm_request({"cmd": "get_state"})
        current_tags = state_resp.get("tag_mask", 0) if state_resp.get("ok") else 0

        resp = _sadewm_request({"cmd": "get_clients"})
        if not resp.get("ok"):
            self._windows = []
            QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)
            return

        clients = resp.get("clients", [])

        # Filter: only minimized windows that share at least one tag with current view
        result = []
        for c in clients:
            if not c.get("minimized", False):
                continue
            win_tags = c.get("tags", 0)
            if current_tags != 0 and (win_tags & current_tags) == 0:
                continue
            win_id = c.get("win_id", 0)
            wm_class = c.get("class", "")
            tags = c.get("tags", 0)
            tag_num = (tags & -tags).bit_length() if tags else 0
            result.append({
                "winId": win_id,
                "name": c.get("name", ""),
                "wmClass": wm_class,
                "tags": tags,
                "tagNum": tag_num,
                "focused": False,
                "minimized": True,
                "iconUri": "",
                "thumbnailUri": "",
            })

        self._windows = result
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

        # Phase 2: capture icons in parallel (thumbnails won't work for minimized windows)
        def _capture(entry):
            win_id = entry["winId"]
            wm_class = entry["wmClass"]
            icon_uri = _net_wm_icon_file_uri(win_id, wm_class)
            return {**entry, "iconUri": icon_uri}

        with ThreadPoolExecutor(max_workers=4) as pool:
            enriched = list(pool.map(_capture, result))

        self._windows = enriched
        QMetaObject.invokeMethod(self, "_emit_changed", Qt.ConnectionType.QueuedConnection)

    @Slot(int)
    def focusWindow(self, win_id: int):
        """Tell the WM to switch to the tag containing win_id and focus it."""
        _sadewm_request({"cmd": "focus_window", "win_id": win_id})
