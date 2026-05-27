"""
Regression tests for EWMH edge cases that sadewm handles internally.
"""

import time

import helpers
from Xlib import X, Xatom
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
