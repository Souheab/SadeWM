"""Single-display regressions; every test uses the private Xvfb desktop fixture."""
import time

import pytest
from Xlib import X, Xatom, XK
from Xlib.ext import xtest
from Xlib.protocol import event

from .test_desktop import desktop as _desktop_fixture, ipc, wait_for, window

desktop = _desktop_fixture


def raw_window(dpy, floating=False):
    win = dpy.screen().root.create_window(
        100, 100, 400, 300, 0, dpy.screen().root_depth,
        X.InputOutput, X.CopyFromParent,
        event_mask=X.StructureNotifyMask | X.KeyPressMask,
    )
    win.set_wm_name("single-monitor-regression")
    if floating:
        win.change_property(dpy.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                            [dpy.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG")])
    return win


def mapped(dpy, win):
    win.map()
    dpy.sync()
    wait_for(lambda: any(c["win_id"] == win.id for c in ipc(cmd="get_clients")["clients"]))
    wait_for(lambda: win.get_attributes().map_state == X.IsViewable)


def active(dpy):
    value = dpy.screen().root.get_full_property(dpy.intern_atom("_NET_ACTIVE_WINDOW"), Xatom.WINDOW)
    return value.value[0] if value else 0


def keyboard_focus(dpy):
    focus = dpy.get_input_focus().focus
    return focus.id if hasattr(focus, "id") else focus


def events(dpy):
    dpy.sync()
    result = []
    while dpy.pending_events():
        result.append(dpy.next_event())
    return result


def key(dpy, name, kind):
    xtest.fake_input(dpy, kind, dpy.keysym_to_keycode(XK.string_to_keysym(name)))


def assert_key_delivery(dpy, win):
    win.change_attributes(event_mask=X.KeyPressMask | X.StructureNotifyMask)
    events(dpy)
    key(dpy, "a", X.KeyPress)
    key(dpy, "a", X.KeyRelease)
    dpy.sync()
    received = []

    def delivered():
        received.extend(events(dpy))
        return any(e.type == X.KeyPress and e.window.id == win.id for e in received)

    wait_for(delivered)


@pytest.mark.parametrize("name,kind,fmt,data", [
    ("WM_HINTS", "WM_HINTS", 32, [1]),
    ("WM_HINTS", "WM_HINTS", 8, b"\x01"),
    ("WM_NORMAL_HINTS", "WM_SIZE_HINTS", 8, bytes(18)),
    ("WM_PROTOCOLS", "ATOM", 8, b"x"),
    ("_NET_WM_STATE", "ATOM", 16, [1]),
    ("_NET_WM_USER_TIME", "CARDINAL", 8, b"\x00"),
    ("WM_TRANSIENT_FOR", "WINDOW", 8, b"x"),
    ("WM_COLORMAP_WINDOWS", "WINDOW", 8, b"x"),
    ("_NET_WM_STRUT_PARTIAL", "CARDINAL", 8, bytes(12)),
])
def test_malformed_properties_do_not_crash(desktop, name, kind, fmt, data):
    dpy, process, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    win = raw_window(dpy)
    atom, type_atom = dpy.intern_atom(name), dpy.intern_atom(kind)
    win.change_property(atom, type_atom, fmt, data)
    mapped(dpy, win)
    # Also exercise property updates and deletion after management.
    win.delete_property(atom)
    dpy.sync()
    win.change_property(atom, type_atom, fmt, data)
    dpy.sync()
    time.sleep(0.08)
    assert process.poll() is None
    assert ipc(cmd="focus_window", win_id=win.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == win.id)


def test_malformed_hints_clear_cached_input_model(desktop):
    dpy, _, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    source = window(dpy)
    win = raw_window(dpy)
    win.set_wm_hints(flags=1, input=0)
    mapped(dpy, win)
    assert active(dpy) == source.id
    win.change_property(Xatom.WM_HINTS, Xatom.WM_HINTS, 32, [1])
    dpy.sync()
    time.sleep(0.05)
    assert ipc(cmd="focus_window", win_id=win.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == win.id)


def test_ipc_focus_uses_fresh_time(desktop):
    dpy, _, _ = desktop
    root = dpy.screen().root
    root.warp_pointer(0, 0)
    source = window(dpy, "source")
    target = window(dpy, "target")
    key(dpy, "Super_L", X.KeyPress)
    key(dpy, "k", X.KeyPress)
    key(dpy, "k", X.KeyRelease)
    key(dpy, "Super_L", X.KeyRelease)
    dpy.sync()
    time.sleep(0.05)
    assert ipc(cmd="focus_window", win_id=source.id)["ok"]
    time.sleep(0.02)
    source.set_input_focus(X.RevertToPointerRoot, X.CurrentTime)
    dpy.sync()
    assert ipc(cmd="focus_window", win_id=target.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == target.id)
    assert active(dpy) == target.id
    assert_key_delivery(dpy, target)


@pytest.mark.parametrize("direct,protocol", [(True, False), (True, True), (False, True), (False, False)])
def test_icccm_focus_models(desktop, direct, protocol):
    dpy, _, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    source = window(dpy, "previous")
    target = raw_window(dpy)
    target.set_wm_hints(flags=1, input=int(direct))
    take_focus = dpy.intern_atom("WM_TAKE_FOCUS")
    if protocol:
        target.set_wm_protocols([take_focus])
    child = target.create_window(5, 5, 100, 80, 0, dpy.screen().root_depth,
                                 X.InputOutput, X.CopyFromParent, event_mask=X.KeyPressMask)
    child.map()
    mapped(dpy, target)
    if not direct and not protocol:
        assert ipc(cmd="focus_window", win_id=target.id)["ok"]
        assert active(dpy) == source.id
        assert keyboard_focus(dpy) == source.id
        return
    wait_for(lambda: active(dpy) == target.id)
    if direct:
        wait_for(lambda: keyboard_focus(dpy) == target.id)
    else:
        assert keyboard_focus(dpy) == source.id
    if protocol:
        messages = []

        def take_focus_received():
            messages.extend(e for e in events(dpy) if e.type == X.ClientMessage
                            and e.window.id == target.id and e.data[1][0] == take_focus)
            return bool(messages)

        wait_for(take_focus_received)
        timestamp = messages[-1].data[1][1]
        assert timestamp != X.CurrentTime
        child.set_input_focus(X.RevertToParent, timestamp)
        dpy.sync()
        time.sleep(0.05)
        assert keyboard_focus(dpy) == child.id
        assert_key_delivery(dpy, child)
    else:
        assert_key_delivery(dpy, target)


def test_focus_protocol_updates(desktop):
    dpy, _, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    source = window(dpy)
    target = raw_window(dpy)
    target.set_wm_hints(flags=1, input=0)
    mapped(dpy, target)
    target.set_wm_protocols([dpy.intern_atom("WM_TAKE_FOCUS")])
    dpy.sync()
    time.sleep(0.05)
    assert ipc(cmd="focus_window", win_id=target.id)["ok"]
    assert active(dpy) == target.id
    target.delete_property(dpy.intern_atom("WM_PROTOCOLS"))
    dpy.sync()
    wait_for(lambda: active(dpy) == source.id)
    target.set_wm_hints(flags=1, input=1)
    dpy.sync()
    time.sleep(0.05)
    assert ipc(cmd="focus_window", win_id=target.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == target.id)


def fullscreen(dpy, win, on):
    dpy.screen().root.send_event(event.ClientMessage(
        window=win, client_type=dpy.intern_atom("_NET_WM_STATE"),
        data=(32, [int(on), dpy.intern_atom("_NET_WM_STATE_FULLSCREEN"), 0, 2, 0])),
        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    dpy.sync()


def geometry(dpy, win):
    geom = win.get_geometry()
    pos = dpy.screen().root.translate_coords(win, 0, 0)
    return pos.x, pos.y, geom.width, geom.height


def test_fullscreen_rejects_configure_and_restores(desktop):
    dpy, _, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    win = window(dpy, style="floating")
    win.change_attributes(event_mask=X.StructureNotifyMask)
    before = geometry(dpy, win)
    fullscreen(dpy, win, True)
    wait_for(lambda: geometry(dpy, win) == (0, 0, 1280, 800))
    events(dpy)
    win.configure(x=150, y=140, width=210, height=160)
    dpy.sync()
    notifications = []

    def acknowledged():
        notifications.extend(e for e in events(dpy)
                             if e.type == X.ConfigureNotify and e.send_event)
        return bool(notifications)

    wait_for(acknowledged)
    assert geometry(dpy, win) == (0, 0, 1280, 800)
    assert (notifications[-1].width, notifications[-1].height) == (1280, 800)
    fullscreen(dpy, win, False)
    wait_for(lambda: geometry(dpy, win) == before)


@pytest.mark.parametrize("user_time", ["zero", "helper_zero", "missing", "malformed", "nonzero"])
@pytest.mark.parametrize("floating", [False, True])
def test_initial_user_time_focus_policy(desktop, user_time, floating):
    dpy, _, _ = desktop
    source = window(dpy, "existing-focus")
    # A new window/retiling appears beneath a stationary pointer.
    dpy.screen().root.warp_pointer(640, 400)
    dpy.sync()
    wait_for(lambda: keyboard_focus(dpy) == source.id)
    target = raw_window(dpy, floating=floating)
    atom = dpy.intern_atom("_NET_WM_USER_TIME")
    if user_time == "helper_zero":
        helper = raw_window(dpy)
        helper.change_property(atom, Xatom.CARDINAL, 32, [0])
        target.change_property(dpy.intern_atom("_NET_WM_USER_TIME_WINDOW"), Xatom.WINDOW, 32, [helper.id])
    elif user_time == "zero":
        target.change_property(atom, Xatom.CARDINAL, 32, [0])
    elif user_time == "malformed":
        target.change_property(atom, Xatom.CARDINAL, 8, b"\0")
    elif user_time == "nonzero":
        target.change_property(atom, Xatom.CARDINAL, 32, [1])
    mapped(dpy, target)
    time.sleep(0.1)
    expected = source if user_time in ("zero", "helper_zero") else target
    assert active(dpy) == expected.id
    assert keyboard_focus(dpy) == expected.id
    # Explicit selection must still work after a suppressed initial focus.
    assert ipc(cmd="focus_window", win_id=target.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == target.id)
    assert_key_delivery(dpy, target)


@pytest.mark.parametrize("resize,tiled", [(False, False), (True, False), (True, True), (False, True)])
def test_drag_burst_applies_final_position(desktop, resize, tiled):
    dpy, _, _ = desktop
    root = dpy.screen().root
    root.warp_pointer(0, 0)
    win = raw_window(dpy, floating=not tiled)
    mapped(dpy, win)
    if tiled:
        other = raw_window(dpy)
        mapped(dpy, other)
    assert ipc(cmd="focus_window", win_id=win.id)["ok"]
    before = geometry(dpy, win)
    win.warp_pointer(100, 100)
    dpy.sync()
    time.sleep(0.05)
    key(dpy, "Super_L", X.KeyPress)
    xtest.fake_input(dpy, X.ButtonPress, 3 if resize else 1)
    dpy.sync()
    time.sleep(0.08)
    pointer = root.query_pointer()
    if tiled:
        end_x = 900
        end_y = 400
    else:
        end_x, end_y = pointer.root_x + 95, pointer.root_y + 65
    # Deliver a whole motion/release burst without giving the WM a chance to
    # complete server round trips between samples.
    dpy.grab_server()
    try:
        xtest.fake_input(dpy, X.MotionNotify, x=end_x - 40, y=end_y - 30)
        xtest.fake_input(dpy, X.MotionNotify, x=end_x, y=end_y)
        xtest.fake_input(dpy, X.ButtonRelease, 3 if resize else 1)
        key(dpy, "Super_L", X.KeyRelease)
        dpy.sync()
    finally:
        dpy.ungrab_server()
        dpy.sync()
    # IPC completion also establishes that the WM left its nested drag loop.
    assert ipc(cmd="get_clients")["ok"]
    after = geometry(dpy, win)
    if tiled and resize:
        # The master ends just before the requested split, allowing gaps/border.
        assert abs(after[0] + after[2] - end_x) < 30
    elif tiled:
        assert after[0] > before[0] + 100
    elif resize:
        assert abs(after[2] - before[2] - 95) <= 3
        assert abs(after[3] - before[3] - 65) <= 3
    else:
        assert after == (before[0] + 95, before[1] + 65, before[2], before[3])


def test_legacy_hints_and_deleted_size_hints(desktop):
    dpy, _, _ = desktop
    dpy.screen().root.warp_pointer(0, 0)
    source = window(dpy)
    target = raw_window(dpy)
    # Legacy WM_HINTS lacks window_group; legacy WM_NORMAL_HINTS lacks base
    # size and gravity. Both representations remain valid.
    target.change_property(Xatom.WM_HINTS, Xatom.WM_HINTS, 32, [1, 0, 0, 0, 0, 0, 0, 0])
    hints = [0] * 15
    hints[0] = (1 << 4) | (1 << 5)
    hints[5:9] = [200, 150, 200, 150]
    target.change_property(Xatom.WM_NORMAL_HINTS, Xatom.WM_SIZE_HINTS, 32, hints)
    mapped(dpy, target)
    actions = dpy.intern_atom("_NET_WM_ALLOWED_ACTIONS")
    resize = dpy.intern_atom("_NET_WM_ACTION_RESIZE")
    assert active(dpy) == source.id
    assert resize not in target.get_full_property(actions, Xatom.ATOM).value
    target.delete_property(Xatom.WM_NORMAL_HINTS)
    dpy.sync()
    wait_for(lambda: resize in target.get_full_property(actions, Xatom.ATOM).value)
    target.delete_property(Xatom.WM_HINTS)
    dpy.sync()
    time.sleep(0.05)
    assert ipc(cmd="focus_window", win_id=target.id)["ok"]
    wait_for(lambda: keyboard_focus(dpy) == target.id)


@pytest.mark.parametrize("existing", [False, True])
def test_unfocused_fullscreen_window_mapping(desktop, existing):
    dpy, _, _ = desktop
    source = window(dpy) if existing else None
    dpy.screen().root.warp_pointer(640, 400)
    dpy.sync()
    target = raw_window(dpy)
    target.change_property(dpy.intern_atom("_NET_WM_USER_TIME"), Xatom.CARDINAL, 32, [0])
    target.change_property(dpy.intern_atom("_NET_WM_STATE"), Xatom.ATOM, 32,
                           [dpy.intern_atom("_NET_WM_STATE_FULLSCREEN")])
    mapped(dpy, target)
    time.sleep(0.1)
    assert active(dpy) == (source.id if source else 0)
    assert keyboard_focus(dpy) == (source.id if source else dpy.screen().root.id)
    # A deliberate click still selects an initially unfocused fullscreen window.
    dpy.screen().root.warp_pointer(0, 0)
    dpy.sync()
    xtest.fake_input(dpy, X.ButtonPress, 1)
    xtest.fake_input(dpy, X.ButtonRelease, 1)
    dpy.sync()
    wait_for(lambda: keyboard_focus(dpy) == target.id)
