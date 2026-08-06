"""
Regression tests for EWMH edge cases that sadewm handles internally.
"""

import shutil
import subprocess
import time

import helpers
import pytest
from Xlib import X, Xatom
from Xlib.protocol import event
from xdrive.window import Window


def _state_atoms(win):
    net_wm_state = win._display.intern_atom("_NET_WM_STATE")
    prop = win._xwindow.get_full_property(net_wm_state, Xatom.ATOM)
    if prop is None:
        return set()
    return set(prop.value.tolist())


def _new_window_with_types(xd, title, atom_names):
    dpy = xd._xdisplay
    root = dpy.screen().root
    screen = dpy.screen()
    xwindow = root.create_window(
        0,
        0,
        400,
        300,
        border_width=0,
        depth=screen.root_depth,
        window_class=X.InputOutput,
        visual=X.CopyFromParent,
        colormap=X.CopyFromParent,
        background_pixel=screen.white_pixel,
        event_mask=(
            X.ExposureMask
            | X.StructureNotifyMask
            | X.FocusChangeMask
            | X.PropertyChangeMask
        ),
    )

    net_wm_name = dpy.intern_atom("_NET_WM_NAME")
    utf8_string = dpy.intern_atom("UTF8_STRING")
    xwindow.change_property(net_wm_name, utf8_string, 8, title.encode("utf-8"))
    xwindow.change_property(Xatom.WM_NAME, Xatom.STRING, 8, title.encode("latin-1"))

    wm_protocols = dpy.intern_atom("WM_PROTOCOLS")
    wm_delete = dpy.intern_atom("WM_DELETE_WINDOW")
    xwindow.change_property(wm_protocols, Xatom.ATOM, 32, [wm_delete])

    net_wm_type = dpy.intern_atom("_NET_WM_WINDOW_TYPE")
    atoms = [dpy.intern_atom(name) for name in atom_names]
    xwindow.change_property(net_wm_type, Xatom.ATOM, 32, atoms)

    xwindow.map()
    dpy.flush()

    win = Window(xwindow, dpy)
    xd.wait_for(lambda: win.is_mapped, timeout=3.0)
    time.sleep(0.2)
    return win


def _send_message(dpy, window, atom_name, values):
    root = dpy.screen().root
    message = event.ClientMessage(
        window=window,
        client_type=dpy.intern_atom(atom_name),
        data=(32, list(values) + [0] * (5 - len(values))),
    )
    root.send_event(
        message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask
    )
    dpy.flush()


def _cardinals(window, dpy, name):
    prop = window.get_full_property(dpy.intern_atom(name), Xatom.CARDINAL)
    return None if prop is None else prop.value.tolist()


def test_fullscreen_and_above_states_are_preserved_independently(xd):
    helpers.ipc_request("view", mask=256)
    time.sleep(0.2)

    win = xd.new_window(title="test-ewmh-state-preserve", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        win.set_state("above")
        time.sleep(0.2)
        win.set_fullscreen(True)
        time.sleep(0.2)

        fullscreen = win._display.intern_atom("_NET_WM_STATE_FULLSCREEN")
        above = win._display.intern_atom("_NET_WM_STATE_ABOVE")

        atoms = _state_atoms(win)
        assert fullscreen in atoms, f"fullscreen state missing after add: {atoms}"
        assert above in atoms, f"above state missing after fullscreen add: {atoms}"

        win.set_fullscreen(False)
        time.sleep(0.2)

        atoms = _state_atoms(win)
        assert fullscreen not in atoms, f"fullscreen state should be removed: {atoms}"
        assert above in atoms, f"above state should be preserved after fullscreen removal: {atoms}"
    finally:
        win.kill()
        time.sleep(0.2)


def test_window_type_dialog_is_respected_when_second_atom(xd):
    helpers.ipc_request("view", mask=128)
    time.sleep(0.2)

    win = _new_window_with_types(
        xd,
        "test-ewmh-type-second",
        ["_NET_WM_WINDOW_TYPE_NORMAL", "_NET_WM_WINDOW_TYPE_DIALOG"],
    )

    try:
        state = helpers.ipc_get_state()
        client = next((c for c in state["clients"] if c["win_id"] == win.id), None)
        assert client is not None, f"test window not managed: {state}"
        assert client["floating"], f"dialog type in second atom should float: {client}"
    finally:
        win.kill()
        time.sleep(0.2)


def test_complete_root_contract_is_published(xd):
    dpy = xd._xdisplay
    root = dpy.screen().root
    required_properties = {
        "_NET_SUPPORTED",
        "_NET_CLIENT_LIST",
        "_NET_CLIENT_LIST_STACKING",
        "_NET_NUMBER_OF_DESKTOPS",
        "_NET_DESKTOP_GEOMETRY",
        "_NET_DESKTOP_VIEWPORT",
        "_NET_CURRENT_DESKTOP",
        "_NET_DESKTOP_NAMES",
        "_NET_ACTIVE_WINDOW",
        "_NET_WORKAREA",
        "_NET_SUPPORTING_WM_CHECK",
        "_NET_SHOWING_DESKTOP",
    }
    for name in required_properties:
        atom = dpy.intern_atom(name)
        assert root.get_full_property(atom, X.AnyPropertyType) is not None, name

    supported_prop = root.get_full_property(
        dpy.intern_atom("_NET_SUPPORTED"), Xatom.ATOM
    )
    supported = set(supported_prop.value.tolist())
    required_supported = {
        "_NET_ACTIVE_WINDOW",
        "_NET_CLOSE_WINDOW",
        "_NET_MOVERESIZE_WINDOW",
        "_NET_WM_MOVERESIZE",
        "_NET_RESTACK_WINDOW",
        "_NET_REQUEST_FRAME_EXTENTS",
        "_NET_SHOWING_DESKTOP",
        "_NET_WM_STATE_FOCUSED",
        "_NET_WM_FULL_PLACEMENT",
    }
    assert {dpy.intern_atom(name) for name in required_supported} <= supported
    assert dpy.intern_atom("_NET_WM_STATE_STAYS_ON_TOP") not in supported
    assert dpy.intern_atom("_NET_WM_ICON") not in supported
    assert dpy.intern_atom("_NET_WM_BYPASS_COMPOSITOR") not in supported
    assert dpy.intern_atom("_NET_WM_WINDOW_OPACITY") not in supported
    if dpy.has_extension("SYNC"):
        assert dpy.intern_atom("_NET_WM_SYNC_REQUEST") in supported
        assert dpy.intern_atom("_NET_WM_SYNC_REQUEST_COUNTER") in supported

    assert _cardinals(root, dpy, "_NET_NUMBER_OF_DESKTOPS") == [9]
    assert len(_cardinals(root, dpy, "_NET_DESKTOP_VIEWPORT")) == 18
    assert len(_cardinals(root, dpy, "_NET_WORKAREA")) == 36


def test_desktop_mapping_and_window_property_contract(xd):
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)
    win = xd.new_window(title="test-ewmh-contract", size=(420, 260), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    try:
        for name, prop_type in (
            ("_NET_WM_DESKTOP", Xatom.CARDINAL),
            ("_NET_WM_STATE", Xatom.ATOM),
            ("_NET_WM_ALLOWED_ACTIONS", Xatom.ATOM),
            ("_NET_FRAME_EXTENTS", Xatom.CARDINAL),
        ):
            assert win._xwindow.get_full_property(dpy.intern_atom(name), prop_type) is not None

        _send_message(dpy, win._xwindow, "_NET_WM_DESKTOP", [3, 2])
        time.sleep(0.2)
        assert _cardinals(win._xwindow, dpy, "_NET_WM_DESKTOP") == [3]

        _send_message(dpy, win._xwindow, "_NET_WM_DESKTOP", [0xFFFFFFFF, 2])
        time.sleep(0.2)
        assert _cardinals(win._xwindow, dpy, "_NET_WM_DESKTOP") == [0xFFFFFFFF]

        root = dpy.screen().root
        _send_message(dpy, root, "_NET_CURRENT_DESKTOP", [5, X.CurrentTime])
        time.sleep(0.2)
        assert _cardinals(root, dpy, "_NET_CURRENT_DESKTOP") == [5]
    finally:
        win.kill()
        helpers.ipc_request("view", mask=1)
        time.sleep(0.2)


def test_show_desktop_and_iconic_lifecycle(xd):
    helpers.ipc_request("view", mask=2)
    time.sleep(0.2)
    win = xd.new_window(title="test-ewmh-lifecycle", size=(400, 260), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    root = dpy.screen().root
    hidden = dpy.intern_atom("_NET_WM_STATE_HIDDEN")
    try:
        _send_message(dpy, root, "_NET_SHOWING_DESKTOP", [1])
        time.sleep(0.2)
        assert _cardinals(root, dpy, "_NET_SHOWING_DESKTOP") == [1]
        assert hidden in _state_atoms(win)
        assert win.is_mapped, "show-desktop must not minimize/unmap ordinary clients"

        _send_message(dpy, root, "_NET_SHOWING_DESKTOP", [0])
        time.sleep(0.2)
        assert hidden not in _state_atoms(win)

        _send_message(dpy, win._xwindow, "WM_CHANGE_STATE", [3])
        time.sleep(0.2)
        wm_state = dpy.intern_atom("WM_STATE")
        state_prop = win._xwindow.get_full_property(wm_state, wm_state)
        assert state_prop.value.tolist()[0] == 3
        assert not win.is_mapped
        assert hidden in _state_atoms(win)

        _send_message(dpy, win._xwindow, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime])
        time.sleep(0.2)
        state_prop = win._xwindow.get_full_property(wm_state, wm_state)
        assert state_prop.value.tolist()[0] == 1
        assert win.is_mapped
        assert hidden not in _state_atoms(win)
    finally:
        win.kill()
        time.sleep(0.2)


def test_initial_iconic_hint_avoids_initial_normal_mapping(xd):
    dpy = xd._xdisplay
    root = dpy.screen().root
    screen = dpy.screen()
    xwindow = root.create_window(
        20,
        20,
        360,
        240,
        border_width=0,
        depth=screen.root_depth,
        window_class=X.InputOutput,
        visual=X.CopyFromParent,
        colormap=X.CopyFromParent,
        event_mask=X.StructureNotifyMask | X.PropertyChangeMask,
    )
    wm_hints = dpy.intern_atom("WM_HINTS")
    wm_state = dpy.intern_atom("WM_STATE")
    # StateHint with initial_state=IconicState. The remaining ICCCM WM_HINTS
    # fields are zero and intentionally carry no additional hints.
    xwindow.change_property(wm_hints, wm_hints, 32, [1 << 1, 0, 3, 0, 0, 0, 0, 0, 0])
    xwindow.map()
    dpy.flush()
    try:
        xd.wait_for(
            lambda: (
                (prop := xwindow.get_full_property(wm_state, wm_state)) is not None
                and prop.value.tolist()[0] == 3
            ),
            timeout=3.0,
        )
        assert xwindow.get_attributes().map_state == X.IsUnmapped

        _send_message(dpy, xwindow, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime])
        xd.wait_for(
            lambda: xwindow.get_attributes().map_state == X.IsViewable,
            timeout=3.0,
        )
        assert xwindow.get_full_property(wm_state, wm_state).value.tolist()[0] == 1
    finally:
        xwindow.destroy()
        dpy.flush()
        time.sleep(0.2)


def test_state_property_deletion_and_opacity_forwarding(xd):
    helpers.ipc_request("view", mask=4)
    time.sleep(0.2)
    win = xd.new_window(title="test-ewmh-owned-properties", size=(410, 270), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    state_atom = dpy.intern_atom("_NET_WM_STATE")
    above = dpy.intern_atom("_NET_WM_STATE_ABOVE")
    opacity = dpy.intern_atom("_NET_WM_WINDOW_OPACITY")
    try:
        win.set_state("above")
        time.sleep(0.2)
        win._xwindow.delete_property(state_atom)
        dpy.flush()
        time.sleep(0.2)
        assert above in _state_atoms(win), "WM-owned state was not republished"

        value = 0x7FFFFFFF
        win._xwindow.change_property(opacity, Xatom.CARDINAL, 32, [value])
        dpy.flush()
        time.sleep(0.2)
        frame_prop = win.frame._xwindow.get_full_property(opacity, Xatom.CARDINAL)
        assert frame_prop is not None and frame_prop.value.tolist() == [value]
    finally:
        win.kill()
        time.sleep(0.2)


@pytest.mark.skipif(shutil.which("wmctrl") is None, reason="wmctrl not installed")
def test_wmctrl_pager_taskbar_smoke(xd):
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)
    win = xd.new_window(title="test-wmctrl-ewmh", size=(400, 260), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    try:
        desktops = subprocess.check_output(["wmctrl", "-d"], text=True)
        assert len([line for line in desktops.splitlines() if line.strip()]) == 9

        subprocess.check_call(["wmctrl", "-r", "test-wmctrl-ewmh", "-t", "2"])
        time.sleep(0.2)
        assert _cardinals(win._xwindow, dpy, "_NET_WM_DESKTOP") == [2]

        subprocess.check_call(["wmctrl", "-s", "2"])
        subprocess.check_call(["wmctrl", "-a", "test-wmctrl-ewmh"])
        time.sleep(0.2)
        assert _cardinals(dpy.screen().root, dpy, "_NET_CURRENT_DESKTOP") == [2]
    finally:
        win.kill()
        helpers.ipc_request("view", mask=1)
        time.sleep(0.2)


def test_xinerama_fullscreen_monitor_indices(multi_monitor_xd):
    xd = multi_monitor_xd
    win = xd.new_window(title="test-fullscreen-monitors", size=(320, 240), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    try:
        supported = dpy.screen().root.get_full_property(
            dpy.intern_atom("_NET_SUPPORTED"), Xatom.ATOM
        ).value.tolist()
        atom = dpy.intern_atom("_NET_WM_FULLSCREEN_MONITORS")
        assert atom in supported

        _send_message(dpy, win._xwindow, "_NET_WM_FULLSCREEN_MONITORS", [0, 1, 0, 1, 2])
        time.sleep(0.2)
        assert _cardinals(win._xwindow, dpy, "_NET_WM_FULLSCREEN_MONITORS") == [0, 1, 0, 1]
        win.set_fullscreen(True)
        time.sleep(0.2)
        assert win.geometry.width >= 800
        assert win.geometry.height >= 600
    finally:
        win.kill()
        time.sleep(0.2)


def test_frame_extents_request_and_stable_client_mapping_order(xd):
    dpy = xd._xdisplay
    root = dpy.screen().root
    screen = dpy.screen()
    raw = root.create_window(
        0, 0, 200, 120, 0, screen.root_depth, X.InputOutput, X.CopyFromParent
    )
    raw.change_property(
        dpy.intern_atom("_NET_WM_WINDOW_TYPE"),
        Xatom.ATOM,
        32,
        [dpy.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG")],
    )
    _send_message(dpy, raw, "_NET_REQUEST_FRAME_EXTENTS", [])
    time.sleep(0.2)
    assert _cardinals(raw, dpy, "_NET_FRAME_EXTENTS") == [0, 0, 28, 0]
    raw.destroy()

    helpers.ipc_request("view", mask=8)
    first = xd.new_window(title="test-map-order-first", size=(300, 200), type="dialog")
    second = xd.new_window(title="test-map-order-second", size=(300, 200), type="dialog")
    xd.wait_for_layout()
    try:
        client_list = root.get_full_property(
            dpy.intern_atom("_NET_CLIENT_LIST"), Xatom.WINDOW
        ).value.tolist()
        assert client_list.index(first.id) < client_list.index(second.id)

        first_geo = first.geometry
        xd.mouse.move(first_geo.x + 20, first_geo.y + first_geo.height - 20)
        xd.mouse.click(button=1)
        xd.wait_for_layout()
        after_focus = root.get_full_property(
            dpy.intern_atom("_NET_CLIENT_LIST"), Xatom.WINDOW
        ).value.tolist()
        assert after_focus == client_list, "focus/raise changed original mapping order"
    finally:
        first.kill()
        second.kill()
        time.sleep(0.2)


def test_override_redirect_dock_live_strut_updates(xd):
    dpy = xd._xdisplay
    root = dpy.screen().root
    screen = dpy.screen()
    dock = root.create_window(
        0,
        0,
        1280,
        80,
        0,
        screen.root_depth,
        X.InputOutput,
        X.CopyFromParent,
        override_redirect=True,
    )
    dock.change_property(
        dpy.intern_atom("_NET_WM_WINDOW_TYPE"),
        Xatom.ATOM,
        32,
        [dpy.intern_atom("_NET_WM_WINDOW_TYPE_DOCK")],
    )
    strut_atom = dpy.intern_atom("_NET_WM_STRUT_PARTIAL")

    def set_top(value):
        dock.change_property(
            strut_atom,
            Xatom.CARDINAL,
            32,
            [0, 0, value, 0, 0, 0, 0, 0, 0, 1279, 0, 0],
        )
        dpy.flush()
        time.sleep(0.2)

    try:
        set_top(90)
        dock.map()
        dpy.flush()
        time.sleep(0.3)
        assert _cardinals(root, dpy, "_NET_WORKAREA")[1] == 90

        set_top(110)
        assert _cardinals(root, dpy, "_NET_WORKAREA")[1] == 110
    finally:
        dock.destroy()
        dpy.flush()
        time.sleep(0.3)
    assert _cardinals(root, dpy, "_NET_WORKAREA")[1] == 40


def test_close_sends_delete_and_timestamped_ping(xd):
    helpers.ipc_request("view", mask=16)
    time.sleep(0.2)
    win = xd.new_window(title="test-ewmh-ping", size=(360, 240), type="dialog")
    xd.wait_for_layout()
    dpy = win._display
    protocols = dpy.intern_atom("WM_PROTOCOLS")
    wm_delete = dpy.intern_atom("WM_DELETE_WINDOW")
    ping = dpy.intern_atom("_NET_WM_PING")
    win._xwindow.change_property(protocols, Xatom.ATOM, 32, [wm_delete, ping])
    dpy.flush()
    while dpy.pending_events():
        dpy.next_event()
    try:
        _send_message(dpy, win._xwindow, "_NET_CLOSE_WINDOW", [X.CurrentTime, 2])
        seen = {}
        deadline = time.time() + 2
        while time.time() < deadline and len(seen) < 2:
            while dpy.pending_events():
                received = dpy.next_event()
                if received.type != X.ClientMessage or received.client_type != protocols:
                    continue
                values = list(received.data[1])
                seen[values[0]] = values
            time.sleep(0.02)
        assert wm_delete in seen
        assert ping in seen
        assert seen[ping][2] == win.id

        values = seen[ping]
        _send_message(dpy, dpy.screen().root, "WM_PROTOCOLS", values)
        time.sleep(0.2)
    finally:
        win.kill()
        time.sleep(0.2)
