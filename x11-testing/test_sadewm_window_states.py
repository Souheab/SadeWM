"""
test_sadewm_window_states.py — xdrive tests for sadewm window state transitions.

Tests:
  1. test_fullscreen_toggle_on_off  — Super+F enters fullscreen; pressing again exits it
  2. test_fullscreen_fills_screen   — fullscreen window geometry covers the whole monitor
  3. test_maximize_toggle           — Super+M expands a tiled window to the work area
  4. test_minimize_restore          — Super+N hides window; Super+Ctrl+N restores it
"""

import time

import helpers  # x11-testing/helpers.py
from xdrive.assertions import expect


# ── Test 1: fullscreen toggle ─────────────────────────────────────────────────


def test_fullscreen_toggle_on_off(xd):
    """Super+F on a focused window sets _NET_WM_STATE_FULLSCREEN; a second press clears it."""
    helpers.ipc_request("view", mask=16)
    time.sleep(0.2)

    win = xd.new_window(title="test-fs-toggle", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # Enter fullscreen
        xd.keyboard.press("super+f")
        xd.wait_for_layout()
        expect(win).to_be_fullscreen()

        # Exit fullscreen
        xd.keyboard.press("super+f")
        xd.wait_for_layout()
        assert not win.is_fullscreen, "Window should NOT be fullscreen after second Super+F"
    finally:
        # Ensure we exit fullscreen before killing (prevents geometry issues)
        if win.is_fullscreen:
            xd.keyboard.press("super+f")
            xd.wait_for_layout()
        win.kill()
        time.sleep(0.2)


# ── Test 2: fullscreen fills the monitor ─────────────────────────────────────


def test_fullscreen_fills_screen(xd):
    """A fullscreen window should cover the entire monitor area (width × height at 0,0)."""
    helpers.ipc_request("view", mask=32)
    time.sleep(0.2)

    win = xd.new_window(title="test-fs-size", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        xd.keyboard.press("super+f")
        xd.wait_for_layout()

        screen_geo = xd.screen.geometry
        win_geo = win.geometry

        assert win_geo.width == screen_geo.width, (
            f"Fullscreen width {win_geo.width} != screen width {screen_geo.width}"
        )
        assert win_geo.height == screen_geo.height, (
            f"Fullscreen height {win_geo.height} != screen height {screen_geo.height}"
        )
        assert win_geo.x == 0, f"Fullscreen x should be 0, got {win_geo.x}"
        assert win_geo.y == 0, f"Fullscreen y should be 0, got {win_geo.y}"
    finally:
        if win.is_fullscreen:
            xd.keyboard.press("super+f")
            xd.wait_for_layout()
        win.kill()
        time.sleep(0.2)


# ── Test 3: maximize expands tiled window to work area ────────────────────────


def test_maximize_toggle(xd):
    """Super+M maximizes a tiled window to the full work area; second press restores it."""
    helpers.ipc_request("view", mask=64)
    time.sleep(0.2)

    # Use a normal (non-dialog) window so it tiles; maximize only applies to tiled windows
    win = xd.new_window(title="test-maximize", size=(400, 300))
    xd.wait_for_layout()

    try:
        geo_before = win.geometry

        # Maximize
        xd.keyboard.press("super+m")
        xd.wait_for_layout()

        geo_max = win.geometry
        screen_geo = xd.screen.geometry

        # Maximized window should start at x=0 (no gap offset) and be wider
        assert geo_max.x < geo_before.x, (
            f"Maximized x={geo_max.x} should be less than tiled x={geo_before.x}"
        )
        assert geo_max.width > geo_before.width, (
            f"Maximized width={geo_max.width} should be greater than tiled width={geo_before.width}"
        )
        # Width should be close to screen width (within 10px for borders)
        assert geo_max.width >= screen_geo.width - 10, (
            f"Maximized width={geo_max.width} should be near screen width={screen_geo.width}"
        )

        # Un-maximize
        xd.keyboard.press("super+m")
        xd.wait_for_layout()

        geo_restored = win.geometry
        assert geo_restored.width < geo_max.width, (
            f"Restored width={geo_restored.width} should be less than maximized {geo_max.width}"
        )
    finally:
        win.kill()
        time.sleep(0.2)


# ── Test 4: minimize and restore ─────────────────────────────────────────────


def test_minimize_restore(xd):
    """Super+N minimizes the focused window; Super+Ctrl+N restores it from the stack."""
    helpers.ipc_request("view", mask=128)
    time.sleep(0.2)

    win = xd.new_window(title="test-minimize", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # Confirm window is initially not minimized
        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        assert client is not None, "Window not found in get_state clients"
        assert not client["minimized"], "Window should not be minimized initially"

        # Minimize
        xd.keyboard.press("super+n")
        xd.wait_for_layout()

        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        assert client is not None, "Window disappeared from get_state after minimize"
        assert client["minimized"], "Window should be minimized after Super+N"

        # Restore
        xd.keyboard.press("super+ctrl+n")
        xd.wait_for_layout()

        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        assert client is not None, "Window disappeared from get_state after restore"
        assert not client["minimized"], "Window should NOT be minimized after Super+Ctrl+N"
    finally:
        # If still minimized, restore before killing so the window can be destroyed cleanly
        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        if client and client["minimized"]:
            xd.keyboard.press("super+ctrl+n")
            xd.wait_for_layout()
        win.kill()
        time.sleep(0.2)
