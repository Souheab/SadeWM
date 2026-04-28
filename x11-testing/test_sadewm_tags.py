"""
test_sadewm_tags.py — xdrive tests for sadewm tag management.

Tests:
  1. test_window_hidden_on_other_tag  — window not visible when viewing a different tag
  2. test_move_window_via_key         — Super+Shift+N reassigns window to the target tag
  3. test_toggleview_shows_both_tags  — toggleview adds a second tag to the current view
"""

import time

import helpers  # x11-testing/helpers.py


# ── Test 1: window invisible on a different tag ───────────────────────────────


def test_window_hidden_on_other_tag(xd):
    """A window on tag 2 should be off-screen when viewing tag 1.

    sadewm keeps all managed windows in _NET_CLIENT_LIST regardless of tag; it
    hides off-tag windows by moving them to a large negative X offset (width*-2).
    Visibility is therefore detected by win.geometry.x >= 0 (on-screen).
    """
    helpers.ipc_request("view", mask=2)
    time.sleep(0.2)

    win = xd.new_window(title="test-tag-hide", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # Window should be on-screen on its own tag
        assert win.geometry.x >= 0, (
            f"Window should be on-screen on its own tag (mask=2), got x={win.geometry.x}"
        )

        # Switch to tag 1 — window on tag 2 should be moved off-screen
        helpers.ipc_request("view", mask=1)
        xd.wait_for_layout()

        assert win.geometry.x < 0, (
            f"Window should be off-screen (x<0) when viewing tag 1, got x={win.geometry.x}"
        )

        # Switch back to tag 2 — window must be on-screen again
        helpers.ipc_request("view", mask=2)
        xd.wait_for_layout()

        assert win.geometry.x >= 0, (
            f"Window should be on-screen again after returning to tag 2, got x={win.geometry.x}"
        )
    finally:
        helpers.ipc_request("view", mask=2)
        time.sleep(0.1)
        win.kill()
        time.sleep(0.2)


# ── Test 2: reassign window to a different tag via key binding ────────────────


def test_move_window_via_key(xd):
    """Super+Shift+5 assigns the focused window to tag 5; it vanishes from tag 3."""
    helpers.ipc_request("view", mask=4)  # tag 3
    time.sleep(0.2)

    win = xd.new_window(title="test-tag-move", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # Verify window starts on tag 3 (mask=4)
        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        assert client is not None, "Window not found in get_state on tag 3"
        assert client["tags"] == 4, f"Expected tags=4 (tag 3), got {client['tags']}"

        # Press Super+Shift+5 to reassign window to tag 5 (mask=16)
        xd.keyboard.press("super+shift+5")
        xd.wait_for_layout()

        # Viewing tag 5 — window must be on-screen
        helpers.ipc_request("view", mask=16)
        xd.wait_for_layout()
        assert win.geometry.x >= 0, (
            f"Window should be on-screen on tag 5 after Super+Shift+5, got x={win.geometry.x}"
        )

        # Viewing tag 3 — window must be off-screen
        helpers.ipc_request("view", mask=4)
        xd.wait_for_layout()
        assert win.geometry.x < 0, (
            f"Window should be off-screen (x<0) on tag 3 after being moved to tag 5, "
            f"got x={win.geometry.x}"
        )
    finally:
        # Ensure we can reach and kill the window (it may be on tag 5)
        helpers.ipc_request("view", mask=16)
        time.sleep(0.1)
        win.kill()
        time.sleep(0.2)


# ── Test 3: toggleview reveals windows from a second tag ─────────────────────


def test_toggleview_shows_both_tags(xd):
    """toggleview(mask=2) while viewing tag 1 shows windows from both tags simultaneously."""
    # Create win1 on tag 1
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)
    win1 = xd.new_window(title="test-tv-win1", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    # Create win2 on tag 2
    helpers.ipc_request("view", mask=2)
    time.sleep(0.2)
    win2 = xd.new_window(title="test-tv-win2", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # On tag 2: win2 on-screen, win1 off-screen
        assert win2.geometry.x >= 0, (
            f"win2 should be on-screen on tag 2, got x={win2.geometry.x}"
        )
        assert win1.geometry.x < 0, (
            f"win1 should be off-screen (x<0) when viewing tag 2 alone, got x={win1.geometry.x}"
        )

        # Toggle tag 1 into the current view (now viewing tags 1 + 2)
        helpers.ipc_request("toggleview", mask=1)
        xd.wait_for_layout()

        assert win1.geometry.x >= 0, (
            f"win1 should be on-screen after toggleview adds tag 1, got x={win1.geometry.x}"
        )
        assert win2.geometry.x >= 0, (
            f"win2 should still be on-screen in combined tag 1+2 view, got x={win2.geometry.x}"
        )
    finally:
        helpers.ipc_request("view", mask=1)
        time.sleep(0.1)
        win1.kill()
        helpers.ipc_request("view", mask=2)
        time.sleep(0.1)
        win2.kill()
        time.sleep(0.2)
