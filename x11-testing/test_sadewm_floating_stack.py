"""Stacking behavior for floating windows and transient dialogs."""

import time

from Xlib import X, Xatom, Xutil

import helpers
from xdrive.window import Window


def _root_children_ids(xd):
    return [child.id for child in xd._xdisplay.screen().root.query_tree().children]


def _assert_above(xd, upper, lower):
    children = _root_children_ids(xd)
    upper_id = upper.frame.id
    lower_id = lower.frame.id
    assert upper_id in children, f"upper frame 0x{upper_id:x} not found in root children"
    assert lower_id in children, f"lower frame 0x{lower_id:x} not found in root children"
    assert children.index(upper_id) > children.index(lower_id), (
        f"expected 0x{upper_id:x} above 0x{lower_id:x}; root children={children}"
    )


def _drain_display_events(dpy):
    while dpy.pending_events():
        dpy.next_event()


def _wait_for_button_press(dpy, win_id, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        while dpy.pending_events():
            ev = dpy.next_event()
            event_window = getattr(ev, "window", None)
            if ev.type == X.ButtonPress and getattr(event_window, "id", None) == win_id:
                return True
        time.sleep(0.02)
    return False


def _create_window(
    xd,
    title,
    *,
    size=(300, 220),
    position=(100, 100),
    window_type="_NET_WM_WINDOW_TYPE_DIALOG",
    transient_for=None,
    state_atoms=None,
    event_mask=X.ExposureMask | X.StructureNotifyMask | X.FocusChangeMask | X.PropertyChangeMask,
):
    dpy = xd._xdisplay
    root = dpy.screen().root
    screen = dpy.screen()
    x, y = position
    w, h = size

    xwin = root.create_window(
        x,
        y,
        w,
        h,
        border_width=0,
        depth=screen.root_depth,
        window_class=X.InputOutput,
        visual=X.CopyFromParent,
        colormap=X.CopyFromParent,
        background_pixel=screen.white_pixel,
        event_mask=event_mask,
    )

    net_wm_name = dpy.intern_atom("_NET_WM_NAME")
    utf8 = dpy.intern_atom("UTF8_STRING")
    xwin.change_property(net_wm_name, utf8, 8, title.encode("utf-8"))
    xwin.change_property(Xatom.WM_NAME, Xatom.STRING, 8, title.encode("latin-1"))

    wm_protocols = dpy.intern_atom("WM_PROTOCOLS")
    wm_delete = dpy.intern_atom("WM_DELETE_WINDOW")
    xwin.change_property(wm_protocols, Xatom.ATOM, 32, [wm_delete])

    if window_type:
        xwin.change_property(
            dpy.intern_atom("_NET_WM_WINDOW_TYPE"),
            Xatom.ATOM,
            32,
            [dpy.intern_atom(window_type)],
        )

    if transient_for is not None:
        xwin.change_property(
            dpy.intern_atom("WM_TRANSIENT_FOR"),
            Xatom.WINDOW,
            32,
            [transient_for.id],
        )

    if state_atoms:
        xwin.change_property(
            dpy.intern_atom("_NET_WM_STATE"),
            Xatom.ATOM,
            32,
            [dpy.intern_atom(atom) for atom in state_atoms],
        )

    xwin.set_wm_normal_hints(
        flags=Xutil.USSize | Xutil.USPosition,
        min_width=w,
        min_height=h,
    )
    xwin.map()
    dpy.flush()

    win = Window(xwin, dpy)
    xd.wait_for(lambda: win.is_mapped, timeout=3.0)
    xd.wait_for_layout()
    return win


def test_clicking_floating_content_raises_and_replays_click(xd):
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)

    lower = _create_window(
        xd,
        "test-click-raise-lower",
        position=(120, 120),
        event_mask=X.ButtonPressMask | X.StructureNotifyMask | X.FocusChangeMask,
    )
    upper = _create_window(xd, "test-click-raise-upper", position=(250, 150))

    try:
        _assert_above(xd, upper, lower)
        _drain_display_events(xd._xdisplay)

        geo = lower.geometry
        xd.mouse.move(geo.x + 30, geo.y + geo.height - 30)
        xd.mouse.click(button=1)

        assert _wait_for_button_press(xd._xdisplay, lower.id), (
            "normal click should be replayed to the floating client after WM raises it"
        )
        xd.wait_for_layout()
        _assert_above(xd, lower, upper)
    finally:
        lower.kill()
        upper.kill()
        time.sleep(0.2)


def test_clicking_selected_but_covered_titlebar_raises_frame(xd):
    helpers.ipc_request("view", mask=2)
    time.sleep(0.2)

    lower = _create_window(xd, "test-titlebar-raise-lower", position=(120, 160))
    upper = _create_window(xd, "test-titlebar-raise-upper", position=(260, 190))

    try:
        # Select and raise lower, then externally disturb stacking so lower is
        # still the WM-selected client but is visually below upper.
        lower_geo = lower.geometry
        xd.mouse.move(lower_geo.x + 30, lower_geo.y + lower_geo.height - 30)
        xd.mouse.click(button=1)
        xd.wait_for_layout()
        _assert_above(xd, lower, upper)

        upper.frame._xwindow.raise_window()
        xd._xdisplay.flush()
        time.sleep(0.1)
        _assert_above(xd, upper, lower)

        frame_geo = lower.frame.geometry
        xd.mouse.move(frame_geo.x + 90, frame_geo.y + 14)
        xd.mouse.click(button=1)
        xd.wait_for_layout()

        _assert_above(xd, lower, upper)
    finally:
        lower.kill()
        upper.kill()
        time.sleep(0.2)


def test_transient_dialog_maps_focused_above_parent(xd):
    helpers.ipc_request("view", mask=4)
    time.sleep(0.2)

    parent = _create_window(xd, "test-transient-parent", position=(160, 140))
    child = None

    try:
        child = _create_window(
            xd,
            "test-transient-child",
            size=(220, 160),
            position=(220, 190),
            transient_for=parent,
        )

        _assert_above(xd, child, parent)
        assert child.is_focused, "new transient dialog should take focus"
    finally:
        if child is not None:
            child.kill()
        parent.kill()
        time.sleep(0.2)


def test_above_window_stays_above_clicked_normal_floating_window(xd):
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)

    above = _create_window(
        xd,
        "test-above-window",
        position=(170, 140),
        state_atoms=["_NET_WM_STATE_ABOVE"],
    )
    normal = _create_window(xd, "test-normal-floating", position=(300, 190))

    try:
        _assert_above(xd, above, normal)

        geo = normal.geometry
        xd.mouse.move(geo.x + 30, geo.y + geo.height - 30)
        xd.mouse.click(button=1)
        xd.wait_for_layout()

        _assert_above(xd, above, normal)
        assert normal.is_focused, "clicked normal floating window should still receive focus"
    finally:
        above.kill()
        normal.kill()
        time.sleep(0.2)
