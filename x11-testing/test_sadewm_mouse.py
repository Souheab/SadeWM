"""
test_sadewm_mouse.py — xdrive-based tests for sadewm mouse behaviour.

Tests:
  1. test_button_press_received — Super+drag triggers movemouse (no "no binding
     matched" in log + window actually moves when floating)
  2. test_tiled_swap — Super+drag swaps master and slave in tiled layout
  3. test_floating_move — Super+drag moves a floating window

Key notes:
- Floating tests use xd.new_window(type="dialog") so sadewm auto-floats them
  at their requested size (400x300).  A window toggled from tiled-to-floating
  retains its full-screen tile dimensions, causing snap-clamp to prevent
  movement; the dialog approach avoids this entirely.
- sadewm INFO log is at ~/.local/share/sadewm/sadewm.log
- DEBUG messages go to FIFO only; INFO log is checked for failure absence

Run via run_tests.sh (which sets up Xvfb + sadewm), or directly:
    pytest x11-testing/test_sadewm_mouse.py -v
"""

import os
import time

import pytest

import helpers  # x11-testing/helpers.py — IPC, WM log helpers

# sadewm's slog file (INFO level, written by LogInit)
LOG = os.path.expanduser("~/.local/share/sadewm/sadewm.log")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _log_size():
    """Return current byte offset in the sadewm log (0 if not found)."""
    try:
        return os.path.getsize(LOG)
    except FileNotFoundError:
        return 0


def _read_new_log(offset):
    """Return log text written after *offset*."""
    try:
        with open(LOG) as f:
            f.seek(offset)
            return f.read()
    except FileNotFoundError:
        return ""


# ── Test 1: button press + movemouse grab works ───────────────────────────────


def test_button_press_received(xd):
    """Super+drag on a managed floating window: movemouse binding must fire.

    Validates that:
    - sadewm does NOT log "no binding matched" (INFO level) for a Super+Button1
      press on a managed window — i.e., the binding matched successfully
    - The window actually moves after the drag (behavioural confirmation that
      GrabPointer + MotionNotify processing all worked end-to-end)

    Uses type="dialog" so sadewm starts it as floating at its requested size.
    This avoids the snap-clamp that prevents movement of full-screen tiled
    windows that have been manually toggled to floating.
    """
    helpers.ipc_request("view", mask=4)
    time.sleep(0.3)

    # Dialog windows are auto-floated at requested size (400x300) by sadewm,
    # so they can be freely dragged without the snap-clamp issue.
    win = xd.new_window(title="test-btn-press", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    geo_before = win.geometry
    sx = geo_before.x + geo_before.width // 2
    sy = geo_before.y + geo_before.height // 2

    log_offset = _log_size()

    # Super+drag 50px right — movemouse should grab and track motion
    with xd.keyboard.held("super"):
        xd.mouse.move(sx, sy)
        time.sleep(0.05)
        xd.mouse.drag(sx, sy, sx + 50, sy, steps=10, step_delay=0.02)

    xd.wait_for_layout()

    new_log = _read_new_log(log_offset)
    assert "no binding matched" not in new_log, (
        "sadewm logged 'no binding matched' — Super+Button1 binding was not found.\n"
        f"Log:\n{new_log}"
    )

    geo_after = win.geometry
    dx = geo_after.x - geo_before.x
    assert dx >= 20, (
        f"Window did not move after Super+drag (dx={dx}). "
        "Possible causes: movemouse grab failed, motion events not delivered."
    )

    win.kill()
    time.sleep(0.2)


# ── Test 2: tiled-mode swap via Super+drag ────────────────────────────────────


def test_tiled_swap(xd):
    """Super+drag master → slave swaps the two tiled windows.

    After the drag the old master window should be located approximately
    at the old slave position, and vice versa (within 50px tolerance).
    """
    helpers.ipc_request("view", mask=1)
    time.sleep(0.3)

    win1 = xd.new_window(title="test-tile-1", size=(400, 300))
    time.sleep(0.4)
    win2 = xd.new_window(title="test-tile-2", size=(400, 300))
    xd.wait_for_layout()

    # Sort by X to identify master (leftmost) and slave
    if win1.geometry.x <= win2.geometry.x:
        master, slave = win1, win2
    else:
        master, slave = win2, win1

    master_geo = master.geometry
    slave_geo = slave.geometry

    sx = master_geo.x + master_geo.width // 2
    sy = master_geo.y + master_geo.height // 2
    ex = slave_geo.x + slave_geo.width // 2
    ey = slave_geo.y + slave_geo.height // 2

    with xd.keyboard.held("super"):
        xd.mouse.drag(sx, sy, ex, ey, steps=20, step_delay=0.015)

    xd.wait_for_layout()

    new_master_geo = master.geometry
    new_slave_geo = slave.geometry

    assert abs(new_master_geo.x - slave_geo.x) < 50, (
        f"Master did not move to slave position: "
        f"got x={new_master_geo.x}, expected ~{slave_geo.x}"
    )
    assert abs(new_slave_geo.x - master_geo.x) < 50, (
        f"Slave did not move to master position: "
        f"got x={new_slave_geo.x}, expected ~{master_geo.x}"
    )

    win1.kill()
    win2.kill()
    time.sleep(0.2)


# ── Test 3: floating-mode move via Super+drag ─────────────────────────────────


def test_floating_move(xd):
    """Super+drag a floating window moves it ~100px right and ~80px down.

    Uses type="dialog" so the window is auto-floated at 400x300 from the start.
    This ensures sadewm places it at its requested size so the snap clamp does
    not prevent movement when dragging.
    The window displacement must be within 30px of (100, 80).
    """
    helpers.ipc_request("view", mask=2)
    time.sleep(0.3)

    # Dialog window: sadewm auto-floats at 400x300, so dragging 100/80px works
    win = xd.new_window(title="test-float-move", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    geo_float = win.geometry
    sx = geo_float.x + geo_float.width // 2
    sy = geo_float.y + geo_float.height // 2
    ex = sx + 100
    ey = sy + 80

    with xd.keyboard.held("super"):
        xd.mouse.drag(sx, sy, ex, ey, steps=15, step_delay=0.015)

    xd.wait_for_layout()

    geo_after = win.geometry
    dx = geo_after.x - geo_float.x
    dy = geo_after.y - geo_float.y

    assert abs(dx - 100) < 30, (
        f"Horizontal displacement off: got dx={dx}, expected ~100"
    )
    assert abs(dy - 80) < 30, (
        f"Vertical displacement off: got dy={dy}, expected ~80"
    )

    win.kill()
    time.sleep(0.2)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
