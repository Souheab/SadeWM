"""FullscreenService — detects fullscreen windows via EWMH properties.

Polls _NET_ACTIVE_WINDOW on the root window and checks whether the focused
window carries _NET_WM_STATE_FULLSCREEN.  The result is exposed as a boolean
QML property so Shell.qml can hide the bar strip on fullscreen applications.
"""

import ctypes
import ctypes.util
import os
import subprocess

from PySide6.QtCore import QObject, Property, Signal, QTimer


def _load_x11():
    """Load libX11, using the same multi-strategy fallback as window_helper."""
    # Fast path: standard locations / ldconfig
    for name in ("X11", "libX11.so.6", "libX11.so"):
        resolved = ctypes.util.find_library(name) or name
        for trial in {resolved, name}:
            try:
                lib = ctypes.CDLL(trial, use_errno=True)
                lib.XOpenDisplay.restype = ctypes.c_void_p
                lib.XDefaultRootWindow.restype = ctypes.c_ulong
                return lib
            except OSError:
                pass

    # NixOS / non-standard prefix fallback: find libX11 via ldd on a Qt lib
    try:
        import PySide6.QtGui as _qtgui
        ldd = subprocess.run(
            ["ldd", _qtgui.__file__],
            capture_output=True, text=True, timeout=5,
        )
        for line in ldd.stdout.splitlines():
            if "libX11.so" in line and "=>" in line:
                raw = line.split("=>")[1].strip().split()[0]
                real = os.path.realpath(raw)
                lib = ctypes.CDLL(real, use_errno=True)
                lib.XOpenDisplay.restype = ctypes.c_void_p
                lib.XDefaultRootWindow.restype = ctypes.c_ulong
                return lib
    except Exception:
        pass

    return None


class FullscreenService(QObject):
    """Exposes a ``hasFullscreen`` bool property to QML.

    Polls every 250 ms.  When the active window gains or loses
    _NET_WM_STATE_FULLSCREEN the ``hasFullscreenChanged`` signal fires so QML
    bindings update immediately.
    """

    hasFullscreenChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_fullscreen = False
        self._libx11 = None
        self._display = None
        self._root = None

        # Cached atom ids (set once in _ensure_ready)
        self._atom_net_active_window = None
        self._atom_net_wm_state = None
        self._atom_net_wm_state_fullscreen = None
        self._atom_net_client_list = None

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_ready(self) -> bool:
        if self._display is not None:
            return True

        self._libx11 = _load_x11()
        if not self._libx11:
            print("FullscreenService: could not load libX11 — fullscreen detection disabled")
            self._timer.stop()
            return False

        raw = self._libx11.XOpenDisplay(None)
        if not raw:
            print("FullscreenService: XOpenDisplay returned NULL")
            return False

        self._display = ctypes.c_void_p(raw)
        self._root = self._libx11.XDefaultRootWindow(self._display)

        self._atom_net_active_window = self._libx11.XInternAtom(
            self._display, b"_NET_ACTIVE_WINDOW", False)
        self._atom_net_wm_state = self._libx11.XInternAtom(
            self._display, b"_NET_WM_STATE", False)
        self._atom_net_wm_state_fullscreen = self._libx11.XInternAtom(
            self._display, b"_NET_WM_STATE_FULLSCREEN", False)
        self._atom_net_client_list = self._libx11.XInternAtom(
            self._display, b"_NET_CLIENT_LIST", False)
        return True

    def _get_window_prop(self, window: int, atom: int) -> int | None:
        """Read a single WINDOW-type X property and return the XID (or None)."""
        XA_WINDOW = 33
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data_ptr = ctypes.c_void_p()

        status = self._libx11.XGetWindowProperty(
            self._display, window, atom,
            0, 1, False, XA_WINDOW,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(nitems),
            ctypes.byref(bytes_after),
            ctypes.byref(data_ptr),
        )
        if status != 0 or not data_ptr.value or nitems.value == 0:
            if data_ptr.value:
                self._libx11.XFree(data_ptr)
            return None
        val = ctypes.c_ulong.from_address(data_ptr.value).value
        self._libx11.XFree(data_ptr)
        return val if val else None

    def _get_window_list(self) -> list[int]:
        """Read _NET_CLIENT_LIST from the root window."""
        XA_WINDOW = 33
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data_ptr = ctypes.c_void_p()

        status = self._libx11.XGetWindowProperty(
            self._display, self._root, self._atom_net_client_list,
            0, 4096, False, XA_WINDOW,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(nitems),
            ctypes.byref(bytes_after),
            ctypes.byref(data_ptr),
        )
        if status != 0 or not data_ptr.value or nitems.value == 0:
            if data_ptr.value:
                self._libx11.XFree(data_ptr)
            return []
        windows = list((ctypes.c_ulong * nitems.value).from_address(data_ptr.value))
        self._libx11.XFree(data_ptr)
        return windows

    def _is_fullscreen(self, window: int) -> bool:
        """Return True if _NET_WM_STATE on *window* includes FULLSCREEN."""
        XA_ATOM = 4
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data_ptr = ctypes.c_void_p()

        status = self._libx11.XGetWindowProperty(
            self._display, window, self._atom_net_wm_state,
            0, 64, False, XA_ATOM,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(nitems),
            ctypes.byref(bytes_after),
            ctypes.byref(data_ptr),
        )
        if status != 0 or not data_ptr.value or nitems.value == 0:
            if data_ptr.value:
                self._libx11.XFree(data_ptr)
            return False
        atoms = list((ctypes.c_ulong * nitems.value).from_address(data_ptr.value))
        self._libx11.XFree(data_ptr)
        return self._atom_net_wm_state_fullscreen in atoms

    def _check_fullscreen(self) -> bool:
        """Return True if a fullscreen window is currently active / visible.

        Primary check: _NET_ACTIVE_WINDOW is fullscreen.
        Fallback: any window in _NET_CLIENT_LIST with a non-negative X
        position (i.e. on-screen) has the fullscreen state.  This handles
        edge cases where focus hasn't been updated yet.
        """
        # Primary: active window
        active = self._get_window_prop(self._root, self._atom_net_active_window)
        if active and self._is_fullscreen(active):
            return True

        # Fallback: scan all clients for a visible fullscreen window.
        # sadewm hides off-tag windows by moving them to x = -(width*2),
        # so we check XGetWindowAttributes.x >= 0 to confirm visibility.
        libx11 = self._libx11
        display = self._display
        for win in self._get_window_list():
            if not self._is_fullscreen(win):
                continue
            # Quick geometry check to confirm the window is on-screen
            root_out = ctypes.c_ulong()
            x = ctypes.c_int()
            y = ctypes.c_int()
            w = ctypes.c_uint()
            h = ctypes.c_uint()
            bw = ctypes.c_uint()
            depth = ctypes.c_uint()
            libx11.XGetGeometry.restype = ctypes.c_int
            ok = libx11.XGetGeometry(
                display, win,
                ctypes.byref(root_out),
                ctypes.byref(x), ctypes.byref(y),
                ctypes.byref(w), ctypes.byref(h),
                ctypes.byref(bw), ctypes.byref(depth),
            )
            if ok and x.value >= 0:
                return True

        return False

    # ------------------------------------------------------------------
    # Timer slot
    # ------------------------------------------------------------------

    def _poll(self):
        if not self._ensure_ready():
            return
        try:
            has_fs = self._check_fullscreen()
            if has_fs != self._has_fullscreen:
                self._has_fullscreen = has_fs
                self.hasFullscreenChanged.emit()
        except Exception as e:
            print(f"FullscreenService: poll error: {e}")

    # ------------------------------------------------------------------
    # QML property
    # ------------------------------------------------------------------

    @Property(bool, notify=hasFullscreenChanged)
    def hasFullscreen(self) -> bool:
        """True when the currently active window is fullscreen."""
        return self._has_fullscreen
