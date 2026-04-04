"""X11 window helper — sets EWMH properties for dock behavior."""

import ctypes
import ctypes.util
import os
import subprocess

from PySide6.QtCore import QObject, QTimer, Slot


def _load_lib(*candidates):
    """Try loading a shared library by several candidate names/paths.

    Tries ctypes.util.find_library first, then each candidate in order.
    Returns the loaded CDLL or raises OSError if none succeeded.
    """
    errors = []
    for name in candidates:
        resolved = ctypes.util.find_library(name) or name
        for trial in {resolved, name}:
            try:
                return ctypes.CDLL(trial, use_errno=True)
            except OSError as e:
                errors.append(f"{trial}: {e}")
    raise OSError(f"Could not load library from candidates {candidates}. Tried: {errors}")


def _find_x11_libs_via_ldd():
    """On NixOS, X11 libraries live in the Nix store and are not in ldconfig.
    Find them by running ldd on a Qt library that links against both libX11 and
    libXext.  Tries several discovery strategies in order.
    Returns (libX11_path, libXext_path) as real absolute paths, or (None, None).
    """
    try:
        import glob

        # Binaries likely to link against libX11 + libXext, ordered by likelihood.
        candidates = []

        # Strategy A: the xcb platform plugin from QT_PLUGIN_PATH (set by wrapQtAppsHook)
        for base_dir in os.environ.get("QT_PLUGIN_PATH", "").split(":"):
            p = os.path.join(base_dir, "platforms", "libqxcb.so")
            if os.path.isfile(p):
                candidates.append(p)

        # Strategy B: xcb plugin under the PySide6 package directory
        try:
            import PySide6
            pkg = os.path.dirname(PySide6.__file__)
            candidates += glob.glob(os.path.join(pkg, "Qt", "plugins", "platforms", "libqxcb.so"))
            candidates += glob.glob(os.path.join(pkg, "**", "libqxcb.so"), recursive=True)
        except Exception:
            pass

        # Strategy C: PySide6.QtGui Python extension module (links against X11)
        try:
            import PySide6.QtGui as _qtgui_mod
            candidates.append(_qtgui_mod.__file__)
        except Exception:
            pass

        x11_path = xext_path = None
        for binary in candidates:
            if not binary or not os.path.isfile(binary):
                continue
            try:
                ldd = subprocess.run(
                    ["ldd", binary], capture_output=True, text=True, timeout=5
                )
            except Exception:
                continue
            for line in ldd.stdout.splitlines():
                if "=>" not in line:
                    continue
                parts = line.split("=>", 1)
                raw = parts[1].strip().split()[0]
                if raw in ("not", ""):
                    continue
                try:
                    real = os.path.realpath(raw)
                except Exception:
                    continue
                base = os.path.basename(real)
                if base.startswith("libX11.so") and x11_path is None:
                    x11_path = real
                elif base.startswith("libXext.so") and xext_path is None:
                    xext_path = real
            if x11_path and xext_path:
                break  # found both, no need to check more binaries

        return x11_path, xext_path
    except Exception:
        return None, None


class WindowHelper(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._wid = None
        self._libx11 = None
        self._libxext = None
        self._libs_ready = False
        self._display = None
        self._raise_timer = None

    def _ensure_libs(self):
        if self._libs_ready:
            return True
        try:
            self._libx11 = _load_lib("X11", "libX11.so.6", "libX11.so")
        except OSError:
            pass

        try:
            self._libxext = _load_lib("Xext", "libXext.so.6", "libXext.so")
        except OSError:
            pass

        # If the fast path failed for either, try ldd-based discovery
        if not self._libx11 or not self._libxext:
            x11_path, xext_path = _find_x11_libs_via_ldd()
            if x11_path and not self._libx11:
                try:
                    self._libx11 = ctypes.CDLL(x11_path, use_errno=True)
                except OSError:
                    pass
            if xext_path and not self._libxext:
                try:
                    self._libxext = ctypes.CDLL(xext_path, use_errno=True)
                except OSError:
                    pass

        self._libs_ready = bool(self._libx11)  # X11 is required; Xext only for shape
        if not self._libx11:
            print("WindowHelper: could not load libX11 — X11 features disabled")
        if not self._libxext:
            print("WindowHelper: could not load libXext — input shape will not be set; "
                  "focus-follows-mouse may be broken")

        # XOpenDisplay returns a 64-bit pointer.  ctypes' default restype is c_int
        # (32-bit), which truncates the pointer and causes SIGSEGV when the truncated
        # value is later passed to functions like XInternAtom.  Fix by declaring the
        # correct restype before first use.
        if self._libx11:
            self._libx11.XOpenDisplay.restype = ctypes.c_void_p

        return self._libs_ready

    @Slot("QVariant")
    def setupX11(self, window):
        """Set X11 EWMH properties to make the window behave as a dock."""
        try:
            if hasattr(window, 'winId'):
                wid = int(window.winId())
            else:
                return
            if not wid:
                print("WindowHelper: winId() returned 0 — skipping X11 setup")
                return
            self._wid = wid
            self._set_x11_properties(wid)
        except Exception as e:
            print(f"WindowHelper.setupX11 error: {e}")

    def _set_x11_properties(self, wid):
        """Use Xlib via ctypes to set window properties."""
        if not self._ensure_libs() or not self._libx11:
            return

        libx11 = self._libx11
        
        # Keep display open for persistent raising
        if not self._display:
            _raw = libx11.XOpenDisplay(None)
            if not _raw:
                print("WindowHelper: XOpenDisplay returned NULL")
                return
            self._display = ctypes.c_void_p(_raw)

        try:
            display = self._display
            
            def intern_atom(name):
                return libx11.XInternAtom(display, name.encode(), False)

            net_wm_window_type      = intern_atom("_NET_WM_WINDOW_TYPE")
            net_wm_window_type_dock = intern_atom("_NET_WM_WINDOW_TYPE_DOCK")
            net_wm_state            = intern_atom("_NET_WM_STATE")
            net_wm_state_above      = intern_atom("_NET_WM_STATE_ABOVE")
            net_wm_state_sticky     = intern_atom("_NET_WM_STATE_STICKY")
            net_wm_strut            = intern_atom("_NET_WM_STRUT")
            net_wm_strut_partial    = intern_atom("_NET_WM_STRUT_PARTIAL")
            xa_atom     = 4  # XA_ATOM
            xa_cardinal = 6  # XA_CARDINAL

            atom_val = ctypes.c_ulong(net_wm_window_type_dock)
            libx11.XChangeProperty(
                display, wid, net_wm_window_type, xa_atom,
                32, 0,
                ctypes.byref(atom_val), 1
            )

            states = (ctypes.c_ulong * 2)(net_wm_state_above, net_wm_state_sticky)
            libx11.XChangeProperty(
                display, wid, net_wm_state, xa_atom,
                32, 0,
                states, 2
            )

            bar_height = 40
            strut = (ctypes.c_ulong * 4)(0, 0, bar_height, 0)
            libx11.XChangeProperty(
                display, wid, net_wm_strut, xa_cardinal,
                32, 0,
                strut, 4
            )

            screen = libx11.XDefaultScreen(display)
            screen_width = libx11.XDisplayWidth(display, screen)
            strut_partial = (ctypes.c_ulong * 12)(
                0, 0, bar_height, 0,
                0, 0, 0, 0,
                0, screen_width - 1,
                0, 0
            )
            libx11.XChangeProperty(
                display, wid, net_wm_strut_partial, xa_cardinal,
                32, 0,
                strut_partial, 12
            )

            # Ensure the window is placed at the top-left of the screen (0,0)
            # Declare proper return types for X11 functions
            libx11.XMoveWindow.restype = ctypes.c_int
            libx11.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
            libx11.XRaiseWindow.restype = ctypes.c_int
            libx11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            
            try:
                # Move window to (0,0) - Window is already created by Qt
                result = libx11.XMoveWindow(display, wid, 0, 0)
                if result == 0:
                    print(f"WindowHelper: XMoveWindow returned error")
                else:
                    print(f"WindowHelper: window positioned at (0,0)")
                
                # Raise to ensure it's on top
                libx11.XRaiseWindow(display, wid)
                
                # Sync to ensure moves are processed
                libx11.XSync(display, False)
                
            except Exception as e:
                print(f"WindowHelper: XMoveWindow/XRaiseWindow failed: {e}")
                # Try to get errno for more details
                try:
                    err = ctypes.get_errno()
                    if err:
                        print(f"  X11 errno: {err}")
                except Exception:
                    pass

            libx11.XFlush(display)
        except Exception as e:
            print(f"WindowHelper._set_x11_properties error: {e}")

        # Start persistent raising timer
        self._start_raise_timer()

    def _start_raise_timer(self):
        """Start a timer to repeatedly raise the window to keep it on top."""
        if not self._wid or not self._ensure_libs() or not self._libx11:
            return
        
        if self._raise_timer is None:
            self._raise_timer = QTimer(self)
            self._raise_timer.timeout.connect(self._raise_window)
            self._raise_timer.start(100)  # Raise every 100ms
            print("WindowHelper: started persistent raising timer")

    def _raise_window(self):
        """Raise the window to ensure it stays on top persistently."""
        if not self._wid or not self._display or not self._libx11:
            return
        
        try:
            libx11 = self._libx11
            libx11.XRaiseWindow.restype = ctypes.c_int
            libx11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            
            libx11.XRaiseWindow(self._display, self._wid)
            libx11.XSync(self._display, False)
        except Exception as e:
            print(f"WindowHelper: error raising window: {e}")

    @Slot("QVariant")
    def setInputRegion(self, rects_variant):
        """Restrict X11 pointer input to the given list of {x,y,width,height} rects.

        Everything outside these rectangles passes input through to windows below,
        keeping WM focus-follows-mouse working over the transparent areas.
        """
        if not self._wid:
            return
        if not self._ensure_libs() or not self._libx11 or not self._libxext:
            return

        try:
            libx11  = self._libx11
            libxext = self._libxext

            rects = rects_variant
            if hasattr(rects_variant, 'toVariant'):
                rects = rects_variant.toVariant()

            class XRectangle(ctypes.Structure):
                _fields_ = [
                    ("x",      ctypes.c_short),
                    ("y",      ctypes.c_short),
                    ("width",  ctypes.c_ushort),
                    ("height", ctypes.c_ushort),
                ]

            n = len(rects)
            if n == 0:
                return
            xrects = (XRectangle * n)()
            for i, r in enumerate(rects):
                if isinstance(r, dict):
                    xrects[i].x      = max(-32768, min(32767,  int(r.get('x',      0))))
                    xrects[i].y      = max(-32768, min(32767,  int(r.get('y',      0))))
                    xrects[i].width  = max(0,      min(65535,  int(r.get('width',  0))))
                    xrects[i].height = max(0,      min(65535,  int(r.get('height', 0))))

            _raw = libx11.XOpenDisplay(None)
            if not _raw:
                return
            # Same pointer-width fix as in _set_x11_properties — must keep as
            # c_void_p so ctypes passes the full 64-bit address, not a truncated int.
            display = ctypes.c_void_p(_raw)
            try:
                ShapeInput = 2
                ShapeSet   = 0
                Unsorted   = 0
                libxext.XShapeCombineRectangles(
                    display, self._wid,
                    ShapeInput, 0, 0,
                    xrects, n,
                    ShapeSet, Unsorted
                )
                libx11.XFlush(display)
            finally:
                libx11.XCloseDisplay(display)
        except Exception as e:
            print(f"WindowHelper.setInputRegion error: {e}")
