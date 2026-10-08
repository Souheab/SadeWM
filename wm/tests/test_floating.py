"""Floating state/input regressions on private X servers only."""
import subprocess
import time

import pytest
from Xlib import X, Xatom, Xutil
from xdrive.window import Window

from wm.tests.test_regression import WM, card, desktop, request, send

pytestmark = pytest.mark.skipif(not WM, reason="WM binary required")


def make_window(xd, *, kind="DIALOG", position=(150, 150), size=(400, 250),
                parent=None, hints=None, properties=()):
    dpy = xd._xdisplay
    root = dpy.screen().root
    raw = root.create_window(*position, *size, 0, X.CopyFromParent, X.InputOutput,
                             X.CopyFromParent, background_pixel=0xeeeeee,
                             event_mask=X.ExposureMask | X.StructureNotifyMask |
                             X.ButtonPressMask | X.ButtonReleaseMask | X.FocusChangeMask)
    raw.set_wm_name("floating regression")
    raw.change_property(dpy.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                        [dpy.intern_atom("_NET_WM_WINDOW_TYPE_" + kind)])
    raw.set_wm_normal_hints(**(hints or {"flags": Xutil.USPosition | Xutil.USSize}))
    if parent is not None:
        raw.set_wm_transient_for(parent._xwindow)
    for name, prop_type, values in properties:
        raw.change_property(dpy.intern_atom(name),
                            dpy.intern_atom(prop_type) if isinstance(prop_type, str) else prop_type,
                            32, values)
    raw.map()
    dpy.sync()
    win = Window(raw, dpy)
    xd.wait_for_layout()
    return win


def settle(xd):
    xd._xdisplay.sync()
    time.sleep(.16)


def drain(dpy):
    events = []
    while dpy.pending_events():
        events.append(dpy.next_event())
    return events


def client(sock, win):
    return next(c for c in request(sock, "get_clients")["clients"] if c["win_id"] == win.id)


def set_state(xd, win, name, on):
    send(xd, win.id, "_NET_WM_STATE", [int(on), xd._xdisplay.intern_atom("_NET_WM_STATE_" + name)])


@pytest.mark.parametrize("fullscreen", [False, True])
def test_repeated_clicks_do_not_expose_or_restack(tmp_path, fullscreen):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        lower = make_window(xd)
        upper = make_window(xd, position=(200, 180))
        if fullscreen:
            set_state(xd, upper, "FULLSCREEN", True)
        xd.mouse.move_to(upper)
        request(sock, "focus_window", win_id=upper.id)
        root = xd._xdisplay.screen().root
        root.change_attributes(event_mask=X.SubstructureNotifyMask)
        settle(xd)
        before = [w.id for w in root.query_tree().children]
        for button in (1, 2, 3, 8, 9):
            drain(xd._xdisplay)
            xd.mouse.click(button=button)
            settle(xd)
            events = drain(xd._xdisplay)
            assert [(e.type, e.detail) for e in events
                    if e.type in (X.ButtonPress, X.ButtonRelease) and e.window.id == upper.id] == [
                        (X.ButtonPress, button), (X.ButtonRelease, button)]
            assert not any(e.type == X.Expose and e.window.id == lower.id for e in events)
            assert not any(e.type == X.ConfigureNotify for e in events)
            assert [w.id for w in root.query_tree().children] == before


@pytest.mark.parametrize("fullscreen", [False, True])
def test_content_click_preserves_widget_focus(tmp_path, fullscreen):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        if fullscreen:
            set_state(xd, win, "FULLSCREEN", True)
        child = win._xwindow.create_window(0, 0, 100, 80, 0, X.CopyFromParent,
                                          X.InputOutput, X.CopyFromParent,
                                          event_mask=X.ButtonPressMask | X.ButtonReleaseMask)
        child.map()
        xd.mouse.move(win.geometry.x + 20, win.geometry.y + 20)
        request(sock, "focus_window", win_id=win.id)
        child.set_input_focus(X.RevertToParent, X.CurrentTime)
        settle(xd)
        drain(xd._xdisplay)
        xd.mouse.click()
        settle(xd)
        assert xd._xdisplay.get_input_focus().focus.id == child.id
        assert any(e.type == X.ButtonPress and e.window.id == child.id for e in drain(xd._xdisplay))


@pytest.mark.parametrize("kind", ["NORMAL", "DIALOG"])
@pytest.mark.parametrize("unshade_in_fullscreen", [False, True])
def test_fullscreen_temporarily_overrides_shading(tmp_path, kind, unshade_in_fullscreen):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind=kind)
        original = win.geometry
        was_floating = client(sock, win)["floating"]
        set_state(xd, win, "SHADED", True)
        assert not win.is_mapped
        set_state(xd, win, "FULLSCREEN", True)
        assert win.is_mapped and win.frame.id == win.id
        assert (win.geometry.x, win.geometry.y, win.geometry.width, win.geometry.height) == (0, 0, 1280, 800)
        if unshade_in_fullscreen:
            set_state(xd, win, "SHADED", False)
            assert win.is_mapped
        set_state(xd, win, "FULLSCREEN", False)
        assert win.is_mapped == unshade_in_fullscreen
        if not unshade_in_fullscreen:
            assert win.frame.id != win.id
            assert win.frame.geometry.height == 38
            set_state(xd, win, "SHADED", False)
        assert win.is_mapped and win.geometry == original
        assert client(sock, win)["floating"] == was_floating


@pytest.mark.parametrize("kind", ["NORMAL", "DIALOG"])
@pytest.mark.parametrize("remove_in_fullscreen", [False, True])
def test_maximize_changed_in_fullscreen_uses_normal_geometry(tmp_path, kind, remove_in_fullscreen):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind=kind)
        original = win.geometry
        set_state(xd, win, "FULLSCREEN", True)
        for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
            set_state(xd, win, axis, True)
        if remove_in_fullscreen:
            for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
                set_state(xd, win, axis, False)
        set_state(xd, win, "FULLSCREEN", False)
        if not remove_in_fullscreen:
            assert client(sock, win)["maximized"]
            for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
                set_state(xd, win, axis, False)
        assert win.geometry == original
        assert not client(sock, win)["maximized"]
        assert client(sock, win)["floating"] == (kind == "DIALOG")


def test_fullscreen_restoration_uses_final_focus_for_stacking(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        set_state(xd, win, "FULLSCREEN", True)
        send(xd, win.id, "WM_CHANGE_STATE", [3])
        peer = make_window(xd, properties=[("_NET_WM_STATE", Xatom.ATOM,
                                           [xd._xdisplay.intern_atom("_NET_WM_STATE_ABOVE")])])
        xd.mouse.move(900, 650)
        xd.keyboard.press("super+ctrl+n")
        settle(xd)
        stack = [w.id for w in xd._xdisplay.screen().root.query_tree().children]
        assert win.is_mapped and win.is_focused and win.is_fullscreen
        assert stack.index(win.frame.id) > stack.index(peer.frame.id)


def test_scanned_iconic_window_restores_then_withdraws(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        process.terminate()
        assert process.wait(timeout=5) == 0
        win = make_window(xd, properties=[("WM_STATE", "WM_STATE", [3, 0])])
        assert win.is_mapped
        restarted = subprocess.Popen([WM, "--no-config"], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            end = time.monotonic() + 5
            while not sock.exists():
                assert restarted.poll() is None and time.monotonic() < end
                time.sleep(.02)
            settle(xd)
            assert client(sock, win)["minimized"] and not win.is_mapped
            request(sock, "focus_window", win_id=win.id)
            settle(xd)
            assert win.is_mapped and win.is_focused
            win._xwindow.unmap()
            settle(xd)
            assert request(sock, "get_clients") == {"ok": True}
        finally:
            restarted.terminate()
            restarted.wait(timeout=5)


@pytest.mark.parametrize("layout_switch", [False, True])
def test_floating_geometry_survives_tile_roundtrip(tmp_path, layout_switch):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind="NORMAL" if layout_switch else "DIALOG")
        request(sock, "focus_window", win_id=win.id)
        if layout_switch:
            xd.keyboard.press("super+shift+f")
            settle(xd)
        win._xwindow.configure(x=180, y=170, width=360, height=240)
        settle(xd)
        original = win.geometry
        xd.keyboard.press("super+t" if layout_switch else "super+ctrl+space")
        settle(xd)
        assert win.geometry != original
        xd.keyboard.press("super+shift+f" if layout_switch else "super+ctrl+space")
        settle(xd)
        assert win.geometry == original


@pytest.mark.parametrize("mode", ["tiled", "floating", "maximized", "fullscreen", "shaded"])
def test_external_move_cancellation_restores_mode_and_geometry(tmp_path, mode):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind="NORMAL" if mode == "tiled" else "DIALOG")
        normal = win.geometry
        if mode == "maximized":
            for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
                set_state(xd, win, axis, True)
        elif mode in ("fullscreen", "shaded"):
            set_state(xd, win, mode.upper(), True)
        original = win.geometry
        flags = card(xd, win._xwindow, "_NET_WM_STATE")
        floating = client(sock, win)["floating"]
        mapped = win.is_mapped
        framed = win.frame.id != win.id
        send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 10, 0, 2])
        xd.keyboard.press("Right")
        xd.keyboard.press("Down")
        xd.keyboard.press("Escape")
        settle(xd)
        assert win.geometry == original
        assert win.is_mapped == mapped
        assert (win.frame.id != win.id) == framed
        assert client(sock, win)["floating"] == floating
        assert card(xd, win._xwindow, "_NET_WM_STATE") == flags
        if mode in ("fullscreen", "shaded"):
            set_state(xd, win, mode.upper(), False)
            assert win.geometry == normal
        elif mode == "maximized":
            for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
                set_state(xd, win, axis, False)
            assert win.geometry == normal
        elif mode == "tiled":
            xd.keyboard.press("super+ctrl+space")
            settle(xd)
            assert (win.geometry.x, win.geometry.y, win.geometry.width, win.geometry.height) == (150, 150, 400, 250)


@pytest.mark.parametrize("kind", ["NORMAL", "DIALOG"])
@pytest.mark.parametrize("protocol_cancel", [False, True])
def test_cancel_discards_pending_sync_resize(tmp_path, kind, protocol_cancel):
    import xcffib
    import xcffib.sync as sync
    with desktop(WM, tmp_path) as (xd, sock, _, env):
        win = make_window(xd, kind=kind)
        original = win.geometry
        connection = xcffib.connect(display=env["DISPLAY"])
        try:
            extension = connection(sync.key)
            extension.Initialize(3, 1).reply()
            counter = connection.generate_id()
            extension.CreateCounter(counter, sync.INT64.synthetic(0, 0), is_checked=True).check()
            atom = xd._xdisplay.intern_atom
            win._xwindow.set_wm_protocols([atom("_NET_WM_SYNC_REQUEST")])
            win._xwindow.change_property(atom("_NET_WM_SYNC_REQUEST_COUNTER"), Xatom.CARDINAL, 32, [counter])
            settle(xd)
            send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 9, 0, 2])
            xd.keyboard.press("Right")
            settle(xd)
            first = win.geometry
            xd.keyboard.press("Right")
            settle(xd)
            assert win.geometry == first
            if protocol_cancel:
                send(xd, win.id, "_NET_WM_MOVERESIZE", [0, 0, 11])
            else:
                xd.keyboard.press("Escape")
            settle(xd)
            assert win.geometry == original
            extension.SetCounter(counter, sync.INT64.synthetic(0, 1), is_checked=True).check()
            time.sleep(1.1)
            assert win.geometry == original
            assert client(sock, win)["floating"] == (kind == "DIALOG")
        finally:
            connection.disconnect()


@pytest.mark.parametrize("grab", ["pointer", "keyboard"])
def test_failed_grab_does_not_convert_window(tmp_path, grab):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind="NORMAL")
        before = (win.geometry, client(sock, win)["floating"], win.frame.id)
        root = xd._xdisplay.screen().root
        if grab == "pointer":
            result = root.grab_pointer(False, X.PointerMotionMask, X.GrabModeAsync,
                                       X.GrabModeAsync, X.NONE, X.NONE, X.CurrentTime)
        else:
            result = root.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
        assert result == X.GrabSuccess
        try:
            send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 10, 0, 2])
            assert (win.geometry, client(sock, win)["floating"], win.frame.id) == before
        finally:
            xd._xdisplay.ungrab_pointer(X.CurrentTime)
            xd._xdisplay.ungrab_keyboard(X.CurrentTime)
            xd._xdisplay.sync()


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("button", [1, 3])
def test_super_drag_restores_maximized_window(tmp_path, cancel, button):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        normal = win.geometry
        for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
            set_state(xd, win, axis, True)
        maximized = win.geometry
        xd.mouse.move(200, 150)
        with xd.keyboard.held("super"):
            xd.mouse.down(button)
            settle(xd)
            xd.mouse.move(600, 420)
            settle(xd)
            during = win.geometry
            assert not client(sock, win)["maximized"]
            if button == 1:
                assert (during.width, during.height) == (normal.width, normal.height)
            if cancel:
                xd.keyboard.press("Escape")
            xd.mouse.up(button)
        settle(xd)
        assert client(sock, win)["maximized"] == cancel
        assert win.geometry == (maximized if cancel else during)


@pytest.mark.parametrize("kind", ["NORMAL", "DIALOG"])
def test_shade_requested_in_fullscreen_applies_on_exit(tmp_path, kind):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, kind=kind)
        original = win.geometry
        set_state(xd, win, "FULLSCREEN", True)
        assert win.is_focused
        set_state(xd, win, "SHADED", True)
        assert win.is_mapped and win.is_focused
        set_state(xd, win, "FULLSCREEN", False)
        assert not win.is_mapped and win.frame.id != win.id
        set_state(xd, win, "SHADED", False)
        assert win.is_mapped and win.geometry == original
        assert client(sock, win)["floating"] == (kind == "DIALOG")


@pytest.mark.parametrize("cancel", [False, True])
def test_titlebar_drag_moves_after_threshold_and_can_cancel(tmp_path, cancel):
    with desktop(WM, tmp_path) as (xd, _, _, _):
        win = make_window(xd, position=(300, 250))
        original = win.geometry
        frame = win.frame.geometry
        xd.mouse.move(frame.x + 120, frame.y + 19)
        xd.mouse.down()
        xd.mouse.move(frame.x + 128, frame.y + 19)
        settle(xd)
        xd.mouse.move(frame.x + 170, frame.y + 59)
        settle(xd)
        assert win.geometry.x == original.x + 50 and win.geometry.y == original.y + 40
        if cancel:
            xd.keyboard.press("Escape")
        xd.mouse.up()
        settle(xd)
        assert (win.geometry == original) == cancel


@pytest.mark.parametrize("fullscreen", [False, True])
def test_drag_restores_normal_size_with_shade_and_maximize(tmp_path, fullscreen):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        normal = win.geometry
        for axis in ("MAXIMIZED_HORZ", "MAXIMIZED_VERT"):
            set_state(xd, win, axis, True)
        set_state(xd, win, "SHADED", True)
        if fullscreen:
            set_state(xd, win, "FULLSCREEN", True)
        original = win.geometry
        flags = card(xd, win._xwindow, "_NET_WM_STATE")
        if fullscreen:
            send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 10, 0, 2])
            xd.keyboard.press("Right")
        else:
            frame = win.frame.geometry
            xd.mouse.move(frame.x + 120, frame.y + 19)
            xd.mouse.down()
            xd.mouse.move(frame.x + 130, frame.y + 19)
        settle(xd)
        assert not client(sock, win)["maximized"]
        assert (win.geometry.width, win.geometry.height) == (normal.width, normal.height)
        xd.keyboard.press("Escape")
        if not fullscreen:
            xd.mouse.up()
        settle(xd)
        assert win.geometry == original
        assert card(xd, win._xwindow, "_NET_WM_STATE") == flags


@pytest.mark.parametrize("hint", ["motif", "gtk"])
def test_decoration_hints_apply_before_mapping_and_dynamically(tmp_path, hint):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        name = "_MOTIF_WM_HINTS" if hint == "motif" else "_GTK_FRAME_EXTENTS"
        prop_type = name if hint == "motif" else Xatom.CARDINAL
        values = [2, 0, 0, 0, 0] if hint == "motif" else [10, 10, 10, 10]
        win = make_window(xd, properties=[(name, prop_type, values)])
        original = win.geometry
        assert win.frame.id == win.id
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [0, 0, 0, 0]
        win._xwindow.delete_property(xd._xdisplay.intern_atom(name))
        settle(xd)
        assert win.frame.id != win.id
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [5, 5, 33, 5]
        assert win.geometry == original
        win._xwindow.change_property(xd._xdisplay.intern_atom(name),
                                    xd._xdisplay.intern_atom(prop_type) if isinstance(prop_type, str) else prop_type,
                                    32, values)
        settle(xd)
        assert win.frame.id == win.id and win.geometry == original


@pytest.mark.parametrize("name,prop_type,values", [
    ("_MOTIF_WM_HINTS", "_MOTIF_WM_HINTS", [0, 0, 0, 0, 0]),
    ("_MOTIF_WM_HINTS", "_MOTIF_WM_HINTS", [2, 0, 1, 0, 0]),
    ("_MOTIF_WM_HINTS", "_MOTIF_WM_HINTS", [2, 0, 0]),
    ("_GTK_FRAME_EXTENTS", Xatom.CARDINAL, [10, 10, 10]),
    ("_GTK_FRAME_EXTENTS", Xatom.ATOM, [10, 10, 10, 10]),
])
def test_invalid_or_enabled_decoration_hints_keep_frame(tmp_path, name, prop_type, values):
    with desktop(WM, tmp_path) as (xd, _, _, _):
        win = make_window(xd, properties=[(name, prop_type, values)])
        assert win.frame.id != win.id
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [5, 5, 33, 5]


def test_frame_changes_preserve_exact_widget_focus(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        child = win._xwindow.create_window(0, 0, 100, 80, 0, X.CopyFromParent,
                                          X.InputOutput, X.CopyFromParent)
        child.map()
        request(sock, "focus_window", win_id=win.id)
        child.set_input_focus(X.RevertToParent, X.CurrentTime)
        settle(xd)
        for fullscreen in (True, False):
            set_state(xd, win, "FULLSCREEN", fullscreen)
            assert xd._xdisplay.get_input_focus().focus.id == child.id
        atom = xd._xdisplay.intern_atom("_MOTIF_WM_HINTS")
        win._xwindow.change_property(atom, atom, 32, [2, 0, 0, 0, 0])
        settle(xd)
        assert xd._xdisplay.get_input_focus().focus.id == child.id
        win._xwindow.delete_property(atom)
        settle(xd)
        assert xd._xdisplay.get_input_focus().focus.id == child.id


@pytest.mark.parametrize("kind", ["MENU", "TOOLTIP", "NOTIFICATION", "SPLASH", "TOOLBAR", "POPUP_MENU"])
def test_special_windows_do_not_get_titlebars(tmp_path, kind):
    with desktop(WM, tmp_path) as (xd, _, _, _):
        win = make_window(xd, kind=kind)
        assert win.frame.id == win.id
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [0, 0, 0, 0]


def test_unpositioned_dialog_centers_over_parent(tmp_path):
    with desktop(WM, tmp_path) as (xd, _, _, _):
        parent = make_window(xd, position=(80, 120), size=(600, 400))
        child = make_window(xd, parent=parent, size=(200, 100), hints={"flags": Xutil.USSize})
        p, c = parent.frame.geometry, child.frame.geometry
        assert abs((p.x + p.width / 2) - (c.x + c.width / 2)) <= 1
        assert abs((p.y + p.height / 2) - (c.y + c.height / 2)) <= 1
        positioned = make_window(xd, parent=parent, position=(700, 500), size=(200, 100))
        assert (positioned.geometry.x, positioned.geometry.y) == (700, 500)
        small_parent = make_window(xd, position=(500, 350), size=(200, 100))
        larger_child = make_window(xd, parent=small_parent, size=(400, 250), hints={"flags": Xutil.USSize})
        p, c = small_parent.frame.geometry, larger_child.frame.geometry
        assert abs((p.x + p.width / 2) - (c.x + c.width / 2)) <= 1
        assert abs((p.y + p.height / 2) - (c.y + c.height / 2)) <= 1


@pytest.mark.parametrize("direction", range(8))
def test_native_border_resize(tmp_path, direction):
    with desktop(WM, tmp_path) as (xd, _, _, _):
        win = make_window(xd, position=(300, 250))
        before = win.geometry
        frame = win.frame.geometry
        points = [(2, 2), (frame.width // 2, 2), (frame.width - 3, 2),
                  (frame.width - 3, frame.height // 2), (frame.width - 3, frame.height - 3),
                  (frame.width // 2, frame.height - 3), (2, frame.height - 3), (2, frame.height // 2)]
        px, py = points[direction]
        dx = -30 if direction in (0, 6, 7) else 30 if direction in (2, 3, 4) else 0
        dy = -20 if direction in (0, 1, 2) else 20 if direction in (4, 5, 6) else 0
        xd.mouse.drag(frame.x + px, frame.y + py, frame.x + px + dx, frame.y + py + dy,
                      steps=5, step_delay=.02)
        settle(xd)
        after = win.geometry
        assert after.width == before.width + abs(dx)
        assert after.height == before.height + abs(dy)
        assert after.x == before.x + min(dx, 0)
        assert after.y == before.y + min(dy, 0)


def test_titlebar_double_click_and_drag_threshold(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd)
        original = win.geometry
        frame = win.frame.geometry
        xd.mouse.move(frame.x + 120, frame.y + 19)
        xd.mouse.down()
        xd.mouse.move(frame.x + 123, frame.y + 21)
        xd.mouse.up()
        settle(xd)
        assert win.geometry == original and not client(sock, win)["maximized"]
        time.sleep(.45)
        xd.mouse.double_click()
        settle(xd)
        assert client(sock, win)["maximized"]
        assert win.frame.geometry.y == 40 and win.frame.geometry.width == 1280
        frame = win.frame.geometry
        xd.mouse.move(frame.x + 120, frame.y + 19)
        time.sleep(.45)
        xd.mouse.double_click()
        settle(xd)
        assert win.geometry == original and not client(sock, win)["maximized"]
        # Pin button clicks must never count as background double clicks.
        frame = win.frame.geometry
        xd.mouse.move(frame.x + 41, frame.y + 19)
        time.sleep(.45)
        xd.mouse.double_click()
        settle(xd)
        assert win.geometry == original and not client(sock, win)["maximized"]


def test_fixed_size_frame_has_no_resize_or_maximize_affordance(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, _, _):
        win = make_window(xd, hints={"flags": Xutil.USPosition | Xutil.PMinSize | Xutil.PMaxSize,
                                    "min_width": 400, "min_height": 250,
                                    "max_width": 400, "max_height": 250})
        original = win.geometry
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [0, 0, 28, 0]
        frame = win.frame.geometry
        xd.mouse.move(frame.x + 120, frame.y + 14)
        xd.mouse.double_click()
        settle(xd)
        assert not client(sock, win)["maximized"] and win.geometry == original
