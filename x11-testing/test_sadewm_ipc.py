"""
test_sadewm_ipc.py — xdrive tests for sadewm IPC socket commands.

Tests:
  1. test_get_state_structure    — get_state returns expected keys + client fields
  2. test_tags_state_structure   — tags_state returns 9 entries with valid state chars
  3. test_ipc_view_switches_tag  — view command updates tag_mask in get_state
  4. test_ipc_focus_window       — focus_window switches tag and focuses the target window
  5. test_ipc_quit_exits_wm      — quit returns ok and exits the WM process
"""

import json
import socket
import time

import helpers  # x11-testing/helpers.py


def _open_tag_subscription():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(helpers.get_socket_path())
    sock.sendall(b'{"cmd":"subscribe_tags"}')
    sock.shutdown(socket.SHUT_WR)
    return sock, sock.makefile("rb")


def _read_tag_event(sock, stream, timeout=2.0):
    sock.settimeout(timeout)
    line = stream.readline()
    if not line:
        raise AssertionError("tag subscription closed before event")
    return json.loads(line.decode())


def _read_until_tag_mask(sock, stream, expected_mask, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        event = _read_tag_event(sock, stream, max(0.05, deadline - time.time()))
        if event.get("event") == "tags_state" and event.get("tag_mask") == expected_mask:
            return event
    raise AssertionError(f"did not receive tag_mask={expected_mask}")


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


def test_subscribe_tags_initial_and_ipc_update(xd):
    """subscribe_tags streams an initial event and pushes IPC view updates."""
    helpers.ipc_request("view", mask=1)
    time.sleep(0.1)

    sock, stream = _open_tag_subscription()
    try:
        initial = _read_tag_event(sock, stream)
        assert initial.get("event") == "tags_state", f"unexpected event: {initial}"
        assert initial.get("tag_mask") == 1, f"unexpected initial mask: {initial}"
        assert "tags_state" in initial, f"missing tags_state: {initial}"

        helpers.ipc_request("view", mask=8)
        event = _read_until_tag_mask(sock, stream, 8)
        assert event["tags_state"][3] == "A", f"tag 4 should be active: {event}"
    finally:
        sock.close()
        helpers.ipc_request("view", mask=1)


def test_subscribe_tags_keyboard_update(xd):
    """subscribe_tags pushes tag changes caused by key bindings."""
    helpers.ipc_request("view", mask=1)
    time.sleep(0.1)

    sock, stream = _open_tag_subscription()
    try:
        _read_tag_event(sock, stream)
        xd.keyboard.press("super+4")
        event = _read_until_tag_mask(sock, stream, 8)
        assert event["tags_state"][3] == "A", f"tag 4 should be active: {event}"
    finally:
        sock.close()
        helpers.ipc_request("view", mask=1)


def test_subscribe_tags_occupied_update(xd):
    """subscribe_tags pushes occupied-state changes after window/tag changes."""
    helpers.ipc_request("view", mask=2)
    time.sleep(0.1)

    sock, stream = _open_tag_subscription()
    win = None
    try:
        _read_tag_event(sock, stream)
        win = xd.new_window(title="test-subscribe-occupied", size=(400, 300), type="dialog")
        xd.wait_for_layout()

        helpers.ipc_request("view", mask=1)
        event = _read_until_tag_mask(sock, stream, 1)
        assert event["tags_state"][1] == "O", f"tag 2 should be occupied: {event}"
    finally:
        sock.close()
        helpers.ipc_request("view", mask=2)
        time.sleep(0.1)
        if win is not None:
            win.kill()
        helpers.ipc_request("view", mask=1)


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


# ── Test 5: quit exits WM cleanly ─────────────────────────────────────────────


def test_ipc_quit_exits_wm(isolated_wm_proc):
    """IPC quit returns ok and causes the sadewm process to exit."""
    resp = helpers.ipc_request("quit")
    assert resp.get("ok") is True, f"quit failed: {resp}"

    deadline = time.time() + 3
    while time.time() < deadline:
        if isolated_wm_proc.poll() is not None:
            return
        time.sleep(0.05)

    assert isolated_wm_proc.poll() is not None, "sadewm did not exit after IPC quit"
