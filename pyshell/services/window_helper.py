"""X11 window helper — sets EWMH properties for dock behavior."""

import ctypes
import ctypes.util
import struct

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QGuiApplication


def _get_x11_display_and_window(qwindow):
    """Get the X11 display pointer and window ID from a QWindow."""
    try:
        iface = QGuiApplication.platformNativeInterface()
        # Get the X11 display
        display = iface.nativeResourceForWindow(b"display", qwindow)
        wid = int(qwindow.winId())
        return display, wid
    except Exception:
        return None, None


class WindowHelper(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot("QVariant")
    def setupX11(self, window):
        """Set X11 EWMH properties to make the window behave as a dock."""
        try:
            from PySide6.QtGui import QWindow

            # Get the actual QWindow from the QML Window
            qwindow = None
            root_objects = window
            # The window argument from QML is the Window item itself, 
            # but we need the underlying QQuickWindow
            # We access the winId via the contentItem's window
            if hasattr(window, 'winId'):
                wid = int(window.winId())
            else:
                return

            self._set_x11_properties(wid)
        except Exception as e:
            print(f"X11 setup error: {e}")

    def _set_x11_properties(self, wid):
        """Use Xlib via ctypes to set window properties."""
        libx11_name = ctypes.util.find_library("X11")
        if not libx11_name:
            return

        libx11 = ctypes.cdll.LoadLibrary(libx11_name)

        # Open display
        display = libx11.XOpenDisplay(None)
        if not display:
            return

        try:
            # Helper to intern atoms
            def intern_atom(name):
                return libx11.XInternAtom(display, name.encode(), False)

            # Atoms
            net_wm_window_type = intern_atom("_NET_WM_WINDOW_TYPE")
            net_wm_window_type_dock = intern_atom("_NET_WM_WINDOW_TYPE_DOCK")
            net_wm_state = intern_atom("_NET_WM_STATE")
            net_wm_state_above = intern_atom("_NET_WM_STATE_ABOVE")
            net_wm_state_sticky = intern_atom("_NET_WM_STATE_STICKY")
            net_wm_strut = intern_atom("_NET_WM_STRUT")
            net_wm_strut_partial = intern_atom("_NET_WM_STRUT_PARTIAL")
            xa_atom = 4  # XA_ATOM
            xa_cardinal = 6  # XA_CARDINAL

            # Set window type to dock
            atom_val = ctypes.c_ulong(net_wm_window_type_dock)
            libx11.XChangeProperty(
                display, wid, net_wm_window_type, xa_atom,
                32, 0,  # PropModeReplace
                ctypes.byref(atom_val), 1
            )

            # Set _NET_WM_STATE: above + sticky
            states = (ctypes.c_ulong * 2)(net_wm_state_above, net_wm_state_sticky)
            libx11.XChangeProperty(
                display, wid, net_wm_state, xa_atom,
                32, 0,
                states, 2
            )

            # Set strut to reserve space at top (40px bar height)
            bar_height = 40
            strut = (ctypes.c_ulong * 4)(0, 0, bar_height, 0)  # left, right, top, bottom
            libx11.XChangeProperty(
                display, wid, net_wm_strut, xa_cardinal,
                32, 0,
                strut, 4
            )

            # Set partial strut
            # Get screen width for the strut
            screen = libx11.XDefaultScreen(display)
            screen_width = libx11.XDisplayWidth(display, screen)
            strut_partial = (ctypes.c_ulong * 12)(
                0, 0, bar_height, 0,  # left, right, top, bottom
                0, 0, 0, 0,          # left_start_y, left_end_y, right_start_y, right_end_y
                0, screen_width - 1,  # top_start_x, top_end_x
                0, 0                  # bottom_start_x, bottom_end_x
            )
            libx11.XChangeProperty(
                display, wid, net_wm_strut_partial, xa_cardinal,
                32, 0,
                strut_partial, 12
            )

            libx11.XFlush(display)
        finally:
            libx11.XCloseDisplay(display)
