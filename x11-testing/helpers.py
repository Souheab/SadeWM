"""
helpers.py — X11 testing helpers for sadewm.

Provides:
  - X11 event injection via python-xlib (ButtonPress, MotionNotify, etc.)
  - IPC client for sadewm's Unix-socket protocol
  - Window discovery and state queries
  - Xdotool wrappers for convenience
"""

import json
import os
import socket
import struct
import subprocess
import time

from Xlib import X, Xatom, display, error

# ── X11 helpers ───────────────────────────────────────────────────────────────

MOD_SUPER = "super"  # Mod4


def open_display(display_name=None):
    """Open an X11 display connection."""
    return display.Display(display_name)


def get_root(dpy):
    """Return the root window of the default screen."""
    return dpy.screen().root


def list_managed_windows(dpy):
    """Return list of (wid, name) for all _NET_CLIENT_LIST windows."""
    root = get_root(dpy)
    atom = dpy.intern_atom("_NET_CLIENT_LIST")
    prop = root.get_full_property(atom, Xatom.WINDOW)
    if prop is None:
        return []
    wids = prop.value.tolist()
    result = []
    for wid in wids:
        win = dpy.create_resource_object("window", wid)
        try:
            name = win.get_wm_name() or ""
        except Exception:
            name = ""
        result.append((wid, name))
    return result


def get_window_geometry(dpy, wid):
    """Return (x, y, w, h) for a window id."""
    win = dpy.create_resource_object("window", wid)
    geom = win.get_geometry()
    # Translate to root coordinates
    coords = win.translate_coords(get_root(dpy), 0, 0)
    return (-coords.x, -coords.y, geom.width, geom.height)


def wait_for_windows(dpy, count, timeout=5.0):
    """Block until at least `count` windows appear in _NET_CLIENT_LIST."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = list_managed_windows(dpy)
        if len(wins) >= count:
            return wins
        time.sleep(0.1)
    raise TimeoutError(
        f"Expected {count} windows, got {len(list_managed_windows(dpy))}"
    )


# ── Low-level X11 event injection via python-xlib ────────────────────────────


def send_button_press(dpy, x, y, button=1, state=0):
    """Inject a ButtonPress event at root-relative (x, y)."""
    root = get_root(dpy)
    # Find which child window is at (x, y)
    child_info = root.query_pointer()

    from Xlib import protocol
    from Xlib.protocol import event as xevent

    evt = xevent.ButtonPress(
        time=X.CurrentTime,
        root=root,
        window=root,
        child=child_info.child or X.NONE,
        root_x=x,
        root_y=y,
        event_x=x,
        event_y=y,
        state=state,
        detail=button,
        same_screen=True,
    )
    root.send_event(evt, event_mask=X.ButtonPressMask)
    dpy.sync()


def send_button_release(dpy, x, y, button=1, state=0):
    """Inject a ButtonRelease event at root-relative (x, y)."""
    root = get_root(dpy)
    child_info = root.query_pointer()

    from Xlib.protocol import event as xevent

    evt = xevent.ButtonRelease(
        time=X.CurrentTime,
        root=root,
        window=root,
        child=child_info.child or X.NONE,
        root_x=x,
        root_y=y,
        event_x=x,
        event_y=y,
        state=state,
        detail=button,
        same_screen=True,
    )
    root.send_event(evt, event_mask=X.ButtonReleaseMask)
    dpy.sync()


# ── xdotool wrappers (more reliable for grab-aware input) ────────────────────


def xdotool(*args):
    """Run xdotool with the given arguments and return stdout."""
    result = subprocess.run(
        ["xdotool"] + list(args),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"xdotool failed: {result.stderr.strip()}")
    return result.stdout.strip()


def move_mouse(x, y):
    """Move the mouse pointer to (x, y)."""
    xdotool("mousemove", str(x), str(y))


def mouse_down(button=1):
    """Press a mouse button (do not release)."""
    xdotool("mousedown", str(button))


def mouse_up(button=1):
    """Release a mouse button."""
    xdotool("mouseup", str(button))


def click(x, y, button=1):
    """Click at (x, y)."""
    move_mouse(x, y)
    xdotool("click", str(button))


def key_down(key):
    """Press a key (do not release)."""
    xdotool("keydown", key)


def key_up(key):
    """Release a key."""
    xdotool("keyup", key)


def drag(start_x, start_y, end_x, end_y, button=1, steps=10, delay_ms=10):
    """
    Simulate a mouse drag from (start_x, start_y) to (end_x, end_y).
    Does NOT hold modifier keys — caller should use key_down/key_up around this.
    """
    move_mouse(start_x, start_y)
    time.sleep(0.05)
    mouse_down(button)
    time.sleep(0.05)
    dx = (end_x - start_x) / steps
    dy = (end_y - start_y) / steps
    for i in range(1, steps + 1):
        nx = int(start_x + dx * i)
        ny = int(start_y + dy * i)
        move_mouse(nx, ny)
        time.sleep(delay_ms / 1000.0)
    time.sleep(0.05)
    mouse_up(button)


def super_drag(start_x, start_y, end_x, end_y, button=1, steps=10, delay_ms=10):
    """
    Simulate Super+ButtonDrag from start to end.
    Holds Super key throughout the drag.
    """
    move_mouse(start_x, start_y)
    time.sleep(0.05)
    key_down("super")
    time.sleep(0.05)
    mouse_down(button)
    time.sleep(0.05)
    dx = (end_x - start_x) / steps
    dy = (end_y - start_y) / steps
    for i in range(1, steps + 1):
        nx = int(start_x + dx * i)
        ny = int(start_y + dy * i)
        move_mouse(nx, ny)
        time.sleep(delay_ms / 1000.0)
    time.sleep(0.05)
    mouse_up(button)
    time.sleep(0.05)
    key_up("super")


# ── Spawn helper windows ─────────────────────────────────────────────────────


def spawn_window(name="test", width=200, height=200):
    """Spawn an xeyes window and return its PID."""
    proc = subprocess.Popen(
        ["xeyes", "-geometry", f"{width}x{height}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def spawn_windows(count, delay=0.4):
    """Spawn multiple test windows and return their PIDs."""
    pids = []
    for i in range(count):
        pids.append(spawn_window(f"test{i}"))
        time.sleep(delay)
    return pids


def kill_pids(pids):
    """Kill a list of PIDs."""
    import signal

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


# ── IPC client ────────────────────────────────────────────────────────────────


def get_socket_path():
    """Return the IPC socket path for the current DISPLAY."""
    if p := os.environ.get("SADEWM_SOCKET"):
        return p
    disp = os.environ.get("DISPLAY", "")
    if not disp:
        return "/tmp/sadewm.sock"
    safe = disp.lstrip(":").replace(".", "-")
    return f"/tmp/sadewm-{safe}.sock"


def ipc_request(cmd, **kwargs):
    """Send an IPC request and return the parsed JSON response."""
    sock_path = get_socket_path()
    payload = json.dumps({"cmd": cmd, **kwargs})
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(sock_path)
        sock.sendall(payload.encode())
        sock.shutdown(socket.SHUT_WR)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    finally:
        sock.close()


def ipc_get_state():
    """Get WM state via IPC."""
    return ipc_request("get_state")


def ipc_view_tag(mask):
    """Switch to a tag by bitmask."""
    return ipc_request("view", mask=mask)


# ── WM log reader ────────────────────────────────────────────────────────────


def read_wm_log(path="/tmp/sadewm_headless.log"):
    """Read the WM log file and return its contents."""
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def tail_wm_log(path="/tmp/sadewm_headless.log", lines=50):
    """Return the last N lines of the WM log."""
    content = read_wm_log(path)
    return "\n".join(content.splitlines()[-lines:])


# ── FIFO state reader ────────────────────────────────────────────────────────


def read_fifo_nonblock(fifo_path=None):
    """Read one line from the sadewm FIFO (non-blocking). Returns None if empty."""
    if fifo_path is None:
        fifo_path = os.path.expanduser("~/.local/share/sadewm/sadewm.fifo")
    try:
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            data = os.read(fd, 4096)
            return data.decode().strip() if data else None
        finally:
            os.close(fd)
    except (OSError, FileNotFoundError):
        return None
