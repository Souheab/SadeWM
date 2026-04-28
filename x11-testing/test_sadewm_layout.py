"""
test_sadewm_layout.py — xdrive tests for sadewm tiling layout mechanics.

Tests:
  1. test_layout_cycle            — Super+Space cycles through available layouts
  2. test_mfact_increase          — Super+Ctrl+L widens the master column
  3. test_mfact_decrease          — Super+Ctrl+H narrows the master column
  4. test_zoom_promotes_to_master — Super+Shift+Return promotes focused slave to master
  5. test_directional_focus       — Super+L moves focus from master to the slave on its right
  6. test_super_resize            — Super+Button3 drag resizes a floating window
"""

import time

import helpers  # x11-testing/helpers.py


def _master_slave(win1, win2):
    """Return (master, slave) by geometry: master is the leftmost window."""
    if win1.geometry.x <= win2.geometry.x:
        return win1, win2
    return win2, win1


# ── Test 1: layout cycle ──────────────────────────────────────────────────────


def test_layout_cycle(xd):
    """Super+Space changes the active layout symbol reported by get_state."""
    helpers.ipc_request("view", mask=256)
    time.sleep(0.2)

    win = xd.new_window(title="test-layout-cycle", size=(400, 300))
    xd.wait_for_layout()

    try:
        state_before = helpers.ipc_get_state()
        # Use (symbol, isrighttiled) because the first cycle step keeps symbol '[]='
        # but flips IsRightTiled: []=left → []=right → ><>
        layout_before = (state_before["layout"], state_before.get("isrighttiled", False))

        xd.keyboard.press("super+space")
        xd.wait_for_layout()

        state_after = helpers.ipc_get_state()
        layout_after = (state_after["layout"], state_after.get("isrighttiled", False))

        assert layout_after != layout_before, (
            f"Layout should change after Super+Space; "
            f"before={layout_before!r}, after={layout_after!r}"
        )

        # Cycle back through remaining layouts to restore original
        xd.keyboard.press("super+space")
        xd.wait_for_layout()
        xd.keyboard.press("super+space")
        xd.wait_for_layout()
    finally:
        win.kill()
        time.sleep(0.2)


# ── Test 2: mfact increase ────────────────────────────────────────────────────


def test_mfact_increase(xd):
    """Super+Ctrl+L increases the master column width."""
    helpers.ipc_request("view", mask=4)
    time.sleep(0.2)

    win1 = xd.new_window(title="test-mfact-up-1", size=(400, 300))
    time.sleep(0.3)
    win2 = xd.new_window(title="test-mfact-up-2", size=(400, 300))
    xd.wait_for_layout()

    try:
        master, _slave = _master_slave(win1, win2)
        width_before = master.geometry.width

        # Increase mfact three times
        for _ in range(3):
            xd.keyboard.press("super+ctrl+l")
            xd.wait_for_layout()

        width_after = master.geometry.width
        assert width_after > width_before, (
            f"Master width should increase after 3× Super+Ctrl+L: "
            f"before={width_before}, after={width_after}"
        )
    finally:
        win1.kill()
        win2.kill()
        time.sleep(0.2)


# ── Test 3: mfact decrease ────────────────────────────────────────────────────


def test_mfact_decrease(xd):
    """Super+Ctrl+H decreases the master column width."""
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)

    win1 = xd.new_window(title="test-mfact-down-1", size=(400, 300))
    time.sleep(0.3)
    win2 = xd.new_window(title="test-mfact-down-2", size=(400, 300))
    xd.wait_for_layout()

    try:
        master, _slave = _master_slave(win1, win2)
        width_before = master.geometry.width

        # Decrease mfact three times
        for _ in range(3):
            xd.keyboard.press("super+ctrl+h")
            xd.wait_for_layout()

        width_after = master.geometry.width
        assert width_after < width_before, (
            f"Master width should decrease after 3× Super+Ctrl+H: "
            f"before={width_before}, after={width_after}"
        )
    finally:
        win1.kill()
        win2.kill()
        time.sleep(0.2)


# ── Test 4: zoom promotes slave to master ─────────────────────────────────────


def test_zoom_promotes_to_master(xd):
    """Super+Shift+Return (Zoom) moves the focused slave window to the master position."""
    helpers.ipc_request("view", mask=16)
    time.sleep(0.2)

    win1 = xd.new_window(title="test-zoom-1", size=(400, 300))
    time.sleep(0.3)
    win2 = xd.new_window(title="test-zoom-2", size=(400, 300))
    xd.wait_for_layout()

    try:
        master, slave = _master_slave(win1, win2)
        slave_x_before = slave.geometry.x

        # Focus the slave via IPC
        resp = helpers.ipc_request("focus_window", win_id=slave.id)
        assert resp.get("ok") is True, f"focus_window failed: {resp}"
        time.sleep(0.3)

        # Zoom: promote focused window to master
        xd.keyboard.press("super+shift+Return")
        xd.wait_for_layout()

        slave_x_after = slave.geometry.x
        master_x_after = master.geometry.x

        # Former slave should now occupy the master (leftmost) position
        assert slave_x_after < slave_x_before, (
            f"After Zoom, former slave should move left (master position): "
            f"x before={slave_x_before}, x after={slave_x_after}"
        )
        # Former master should now be to the right of the former slave
        assert master_x_after > slave_x_after, (
            f"After Zoom, former master should be right of former slave: "
            f"master_x={master_x_after}, slave_x={slave_x_after}"
        )
    finally:
        win1.kill()
        win2.kill()
        time.sleep(0.2)


# ── Test 5: directional focus ─────────────────────────────────────────────────


def test_directional_focus(xd):
    """Super+L (FocusRight) moves keyboard focus from the master to the slave."""
    helpers.ipc_request("view", mask=32)
    time.sleep(0.2)

    win1 = xd.new_window(title="test-dir-focus-1", size=(400, 300))
    time.sleep(0.3)
    win2 = xd.new_window(title="test-dir-focus-2", size=(400, 300))
    xd.wait_for_layout()

    try:
        master, slave = _master_slave(win1, win2)

        # Focus the master (left column) via IPC
        resp = helpers.ipc_request("focus_window", win_id=master.id)
        assert resp.get("ok") is True, f"focus_window failed: {resp}"
        time.sleep(0.3)

        # Confirm master is focused in WM state
        state = helpers.ipc_get_state()
        focused_id = next((c["win_id"] for c in state["clients"] if c["focused"]), None)
        assert focused_id == master.id, (
            f"Master (id={master.id}) should be focused before Super+L; "
            f"got focused_id={focused_id}"
        )

        # Press Super+L → FocusRight
        xd.keyboard.press("super+l")
        xd.wait_for_layout()

        # Slave should now be focused
        state = helpers.ipc_get_state()
        focused_id = next((c["win_id"] for c in state["clients"] if c["focused"]), None)
        assert focused_id == slave.id, (
            f"After Super+L, slave (id={slave.id}) should be focused; "
            f"got focused_id={focused_id}"
        )
    finally:
        win1.kill()
        win2.kill()
        time.sleep(0.2)


# ── Test 6: Super+Button3 drag resizes a floating window ──────────────────────


def test_super_resize(xd):
    """Super+Button3 drag outward from the window's bottom-right quadrant increases its size."""
    helpers.ipc_request("view", mask=64)
    time.sleep(0.2)

    win = xd.new_window(title="test-resize", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        geo = win.geometry
        # Start near the bottom-right quadrant so sadewm picks the BR corner
        sx = geo.x + geo.width * 3 // 4
        sy = geo.y + geo.height * 3 // 4
        ex = sx + 100
        ey = sy + 80

        with xd.keyboard.held("super"):
            xd.mouse.drag(sx, sy, ex, ey, steps=15, step_delay=0.015, button=3)

        xd.wait_for_layout()

        geo_after = win.geometry
        assert geo_after.width > geo.width, (
            f"Width should increase after Super+Button3 resize: "
            f"before={geo.width}, after={geo_after.width}"
        )
        assert geo_after.height > geo.height, (
            f"Height should increase after Super+Button3 resize: "
            f"before={geo.height}, after={geo_after.height}"
        )
    finally:
        win.kill()
        time.sleep(0.2)
