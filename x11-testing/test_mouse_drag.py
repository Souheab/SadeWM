#!/usr/bin/env python3
"""
test_mouse_drag.py — Validate Super+Button1 drag behaviour in sadewm-go.

Tests:
  1. Tiled mode: Super+drag swaps windows in the direction of the drag
  2. Floating mode: Super+drag moves the floating window

Requires: DISPLAY set, sadewm running, xdotool, python3-xlib, xeyes.
"""

import os
import sys
import time

# Allow importing helpers from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

LOG = "/tmp/sadewm_headless.log"
PASS = 0
FAIL = 0


def log(msg):
    print(f"  {msg}")


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {name}")
        PASS += 1
    else:
        extra = f" — {detail}" if detail else ""
        print(f"  ✗ {name}{extra}")
        FAIL += 1
    return condition


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Tiled-mode swap via Super+Drag
# ─────────────────────────────────────────────────────────────────────────────


def test_tiled_swap():
    """
    Open two tiled windows.  Super+drag the master window into the slave area.
    Expect the two windows to swap positions in the client list.
    """
    print("\n── Test: tiled swap via Super+Drag ────────────────────────────")

    dpy = helpers.open_display()

    # Ensure we're on tag 1 in tiled layout
    helpers.ipc_request("view", mask=1)
    time.sleep(0.3)

    # Spawn two windows so we get a master + stack layout
    pids = helpers.spawn_windows(2, delay=0.5)
    time.sleep(0.5)

    wins = helpers.wait_for_windows(dpy, 2, timeout=3)
    check("two windows managed", len(wins) >= 2, f"got {len(wins)}")

    if len(wins) < 2:
        helpers.kill_pids(pids)
        dpy.close()
        return

    # Read geometry of the two tiled windows
    geoms = {}
    for wid, name in wins:
        geoms[wid] = helpers.get_window_geometry(dpy, wid)
    log(f"window geometries: {geoms}")

    # Identify master (leftmost x) and slave
    sorted_wins = sorted(geoms.items(), key=lambda kv: kv[1][0])
    master_wid = sorted_wins[0][0]
    slave_wid = sorted_wins[1][0]
    master_geom = sorted_wins[0][1]
    slave_geom = sorted_wins[1][1]
    log(f"master=0x{master_wid:x} at {master_geom}")
    log(f"slave =0x{slave_wid:x} at {slave_geom}")

    # Get initial client order from IPC
    state_before = helpers.ipc_get_state()
    log(f"state before: {state_before}")

    # Calculate drag: from center of master to center of slave
    sx = master_geom[0] + master_geom[2] // 2
    sy = master_geom[1] + master_geom[3] // 2
    ex = slave_geom[0] + slave_geom[2] // 2
    ey = slave_geom[1] + slave_geom[3] // 2
    log(f"drag from ({sx},{sy}) → ({ex},{ey})")

    # Perform Super+Button1 drag
    helpers.super_drag(sx, sy, ex, ey, button=1, steps=20, delay_ms=15)
    time.sleep(0.5)

    # After swap, geometries should have exchanged
    new_master_geom = helpers.get_window_geometry(dpy, master_wid)
    new_slave_geom = helpers.get_window_geometry(dpy, slave_wid)
    log(f"after drag: master=0x{master_wid:x} at {new_master_geom}")
    log(f"after drag: slave =0x{slave_wid:x} at {new_slave_geom}")

    # The old master should now be roughly where the slave was (and vice versa)
    master_moved = abs(new_master_geom[0] - slave_geom[0]) < 50
    slave_moved = abs(new_slave_geom[0] - master_geom[0]) < 50
    check(
        "master swapped to slave position",
        master_moved,
        f"new x={new_master_geom[0]}, expected ~{slave_geom[0]}",
    )
    check(
        "slave swapped to master position",
        slave_moved,
        f"new x={new_slave_geom[0]}, expected ~{master_geom[0]}",
    )

    # Also check IPC state changed
    state_after = helpers.ipc_get_state()
    log(f"state after: {state_after}")

    # Print relevant log lines
    wm_log = helpers.tail_wm_log(LOG, 30)
    if wm_log:
        log("--- WM log (last 30 lines) ---")
        for line in wm_log.splitlines():
            log(f"  | {line}")

    helpers.kill_pids(pids)
    time.sleep(0.3)
    dpy.close()


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Floating-mode move via Super+Drag
# ─────────────────────────────────────────────────────────────────────────────


def test_floating_move():
    """
    Open one window, toggle it to floating, then Super+drag it.
    Expect the window to move to the new position.
    """
    print("\n── Test: floating move via Super+Drag ─────────────────────────")

    dpy = helpers.open_display()

    # Switch to tag 2 to isolate from previous test
    helpers.ipc_request("view", mask=2)
    time.sleep(0.3)

    pids = helpers.spawn_windows(1, delay=0.5)
    time.sleep(0.5)

    wins = helpers.wait_for_windows(dpy, 1, timeout=3)
    check("one window managed", len(wins) >= 1, f"got {len(wins)}")

    if len(wins) < 1:
        helpers.kill_pids(pids)
        dpy.close()
        return

    wid = wins[0][0]
    geom_before = helpers.get_window_geometry(dpy, wid)
    log(f"window 0x{wid:x} at {geom_before}")

    # Toggle floating via keyboard shortcut (Super+Ctrl+Space)
    helpers.xdotool("key", "super+ctrl+space")
    time.sleep(0.3)

    geom_float = helpers.get_window_geometry(dpy, wid)
    log(f"after toggle floating: {geom_float}")

    # Drag from center of window ≈100px right and ≈80px down
    sx = geom_float[0] + geom_float[2] // 2
    sy = geom_float[1] + geom_float[3] // 2
    ex = sx + 100
    ey = sy + 80
    log(f"drag from ({sx},{sy}) → ({ex},{ey})")

    helpers.super_drag(sx, sy, ex, ey, button=1, steps=15, delay_ms=15)
    time.sleep(0.5)

    geom_after = helpers.get_window_geometry(dpy, wid)
    log(f"after drag: {geom_after}")

    dx = geom_after[0] - geom_float[0]
    dy = geom_after[1] - geom_float[1]
    log(f"displacement: dx={dx} dy={dy}")

    check("window moved horizontally", abs(dx - 100) < 30, f"dx={dx}, expected ~100")
    check("window moved vertically", abs(dy - 80) < 30, f"dy={dy}, expected ~80")

    wm_log = helpers.tail_wm_log(LOG, 30)
    if wm_log:
        log("--- WM log (last 30 lines) ---")
        for line in wm_log.splitlines():
            log(f"  | {line}")

    helpers.kill_pids(pids)
    time.sleep(0.3)
    dpy.close()


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Basic button press reaches WM
# ─────────────────────────────────────────────────────────────────────────────


def test_button_press_received():
    """
    Open a window, do Super+click (no drag). Verify the WM log shows
    the button press was received and an action was matched.
    """
    print("\n── Test: button press received by WM ──────────────────────────")

    dpy = helpers.open_display()
    helpers.ipc_request("view", mask=4)
    time.sleep(0.3)

    # Truncate log to only capture new entries
    try:
        log_size_before = os.path.getsize(LOG)
    except FileNotFoundError:
        log_size_before = 0

    pids = helpers.spawn_windows(1, delay=0.5)
    time.sleep(0.5)

    wins = helpers.wait_for_windows(dpy, 1, timeout=3)
    if not wins:
        log("no window managed, skipping")
        helpers.kill_pids(pids)
        dpy.close()
        return

    wid = wins[0][0]
    geom = helpers.get_window_geometry(dpy, wid)

    cx = geom[0] + geom[2] // 2
    cy = geom[1] + geom[3] // 2
    log(f"clicking Super+Button1 at ({cx},{cy}) on window 0x{wid:x}")

    helpers.move_mouse(cx, cy)
    time.sleep(0.1)
    helpers.key_down("super")
    time.sleep(0.05)
    helpers.mouse_down(1)
    time.sleep(0.2)
    helpers.mouse_up(1)
    time.sleep(0.05)
    helpers.key_up("super")
    time.sleep(0.3)

    # Read new log entries
    try:
        with open(LOG) as f:
            f.seek(log_size_before)
            new_log = f.read()
    except FileNotFoundError:
        new_log = ""

    has_buttonpress = "buttonpress:" in new_log
    has_action = 'matched action="movemouse"' in new_log or "MoveMouse:" in new_log
    has_grab = "GrabPointer" in new_log

    check("WM received buttonpress", has_buttonpress, "no 'buttonpress:' in log")
    check("movemouse action matched", has_action, "no movemouse in log")
    check("GrabPointer was called", has_grab, "no GrabPointer in log")

    if new_log.strip():
        log("--- new WM log entries ---")
        for line in new_log.strip().splitlines():
            log(f"  | {line}")

    helpers.kill_pids(pids)
    time.sleep(0.3)
    dpy.close()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("sadewm-go Mouse Drag Tests")
    print("=" * 70)

    test_button_press_received()
    test_tiled_swap()
    test_floating_move()

    print("\n" + "=" * 70)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 70)
    sys.exit(1 if FAIL > 0 else 0)
