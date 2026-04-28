"""
test_sadewm_ipc.py — xdrive tests for sadewm IPC socket commands.

Tests:
  1. test_get_state_structure    — get_state returns expected keys + client fields
  2. test_tags_state_structure   — tags_state returns 9 entries with valid state chars
  3. test_ipc_view_switches_tag  — view command updates tag_mask in get_state
  4. test_ipc_focus_window       — focus_window switches tag and focuses the target window
"""

import time

import helpers  # x11-testing/helpers.py


# ── Test 1: get_state response structure ──────────────────────────────────────


def test_get_state_structure(xd):
    """get_state returns a dict with all expected top-level and per-client keys."""
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)

    win = xd.new_window(title="test-ipc-state", size=(400, 300))
    xd.wait_for_layout()

    try:
        state = helpers.ipc_get_state()

        assert state.get("ok") is True, f"'ok' field missing or False: {state}"
        for key in ("tag_mask", "layout", "mfact", "nmaster", "gaps", "clients"):
            assert key in state, f"Missing key '{key}' in get_state response: {state}"

        clients = state["clients"]
        assert len(clients) >= 1, "Expected at least one client in get_state"

        client = clients[0]
        for key in ("name", "win_id", "tags", "floating", "maximized", "focused", "minimized"):
            assert key in client, f"Missing client key '{key}': {client}"
    finally:
        win.kill()
        time.sleep(0.2)


# ── Test 2: tags_state response structure ─────────────────────────────────────


def test_tags_state_structure(xd):
    """tags_state returns exactly 9 state strings, each a valid state char."""
    resp = helpers.ipc_request("tags_state")

    assert resp.get("ok") is True, f"'ok' field missing or False: {resp}"
    assert "tags_state" in resp, f"Missing 'tags_state' key in response: {resp}"

    states = resp["tags_state"]
    assert len(states) == 9, f"Expected 9 tag states, got {len(states)}: {states}"

    valid = {"U", "A", "O", "I"}
    for i, s in enumerate(states):
        assert s in valid, f"Tag {i} has unexpected state {s!r} (valid: {valid})"


# ── Test 3: view command updates tag_mask ─────────────────────────────────────


def test_ipc_view_switches_tag(xd):
    """IPC view command changes the active tag mask reported by get_state."""
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)

    state = helpers.ipc_get_state()
    assert state["tag_mask"] == 8, (
        f"Expected tag_mask=8 after view mask=8, got {state['tag_mask']}"
    )

    helpers.ipc_request("view", mask=16)
    time.sleep(0.2)

    state = helpers.ipc_get_state()
    assert state["tag_mask"] == 16, (
        f"Expected tag_mask=16 after view mask=16, got {state['tag_mask']}"
    )

    # Restore to tag 1
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)


# ── Test 4: focus_window switches tag and focuses the window ──────────────────


def test_ipc_focus_window(xd):
    """focus_window IPC switches to the target window's tag and gives it focus."""
    # Create win1 on tag 3 (mask=4)
    helpers.ipc_request("view", mask=4)
    time.sleep(0.2)
    win1 = xd.new_window(title="test-ipc-focus-a", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    # Create win2 on tag 4 (mask=8); this becomes the active tag
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)
    win2 = xd.new_window(title="test-ipc-focus-b", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        # Currently on tag 4 with win2 visible; ask WM to focus win1 (on tag 3)
        resp = helpers.ipc_request("focus_window", win_id=win1.id)
        assert resp.get("ok") is True, f"focus_window failed: {resp}"
        time.sleep(0.3)

        # Tag should have switched to tag 3 (mask=4)
        state = helpers.ipc_get_state()
        assert state["tag_mask"] == 4, (
            f"Expected tag_mask=4 after focus_window on tag-3 window, "
            f"got {state['tag_mask']}"
        )

        # win1 should be marked focused in WM state
        focused = next((c for c in state["clients"] if c["focused"]), None)
        assert focused is not None, "No focused client in get_state after focus_window"
        assert focused["win_id"] == win1.id, (
            f"Expected win1 (id={win1.id}) to be focused, "
            f"got win_id={focused['win_id']}"
        )
    finally:
        # Kill win1 (currently visible on tag 3)
        win1.kill()
        # Switch to tag 4 to kill win2
        helpers.ipc_request("view", mask=8)
        time.sleep(0.1)
        win2.kill()
        time.sleep(0.2)
