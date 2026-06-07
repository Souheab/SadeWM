"""Protocol-level checks for floating frames and tiled border companions."""

import time

from Xlib import X, Xatom

import helpers
from xdrive.assertions import expect


TITLEBAR_HEIGHT = 28


def _frame_extents(win):
    atom = win._display.intern_atom("_NET_FRAME_EXTENTS")
    prop = win._xwindow.get_full_property(atom, Xatom.CARDINAL)
    assert prop is not None, "_NET_FRAME_EXTENTS should be published"
    return list(prop.value)


def _parent_id(win):
    return win._xwindow.query_tree().parent.id


def test_floating_dialog_uses_reparented_titlebar_frame(xd):
    helpers.ipc_request("view", mask=1)
    time.sleep(0.2)

    win = xd.new_window(title="test-floating-frame", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        expect(win).to_be_reparented()
        frame = win.frame
        client_geo = win.geometry
        frame_geo = frame.geometry
        child_ids = {child.id for child in frame._xwindow.query_tree().children}

        assert frame_geo.x == client_geo.x
        assert frame_geo.y == client_geo.y - TITLEBAR_HEIGHT
        assert frame_geo.width == client_geo.width
        assert frame_geo.height == client_geo.height + TITLEBAR_HEIGHT
        assert win.id in child_ids
        assert len(child_ids - {win.id}) == 1, "frame should contain one titlebar child"
        assert _frame_extents(win) == [0, 0, TITLEBAR_HEIGHT, 0]

        win.set_size(460, 340)
        xd.wait_for_layout()
        client_geo = win.geometry
        frame_geo = win.frame.geometry
        assert (client_geo.width, client_geo.height) == (460, 340)
        assert frame_geo.width == client_geo.width
        assert frame_geo.height == client_geo.height + TITLEBAR_HEIGHT
    finally:
        win.kill()
        time.sleep(0.2)


def test_tiled_window_keeps_root_level_border_companion(xd):
    helpers.ipc_request("view", mask=2)
    time.sleep(0.2)

    win = xd.new_window(title="test-tiled-border", size=(400, 300))
    xd.wait_for_layout()

    try:
        root = win._display.screen().root
        client_geo = win.geometry
        assert _parent_id(win) == root.id
        assert _frame_extents(win) == [0, 0, 0, 0]

        border_matches = []
        for child in root.query_tree().children:
            if child.id == win.id:
                continue
            attrs = child.get_attributes()
            geo = child.get_geometry()
            translated = child.translate_coords(root, 0, 0)
            x, y = -translated.x, -translated.y
            if (
                attrs.override_redirect
                and attrs.map_state == X.IsViewable
                and x == client_geo.x - 2
                and y == client_geo.y - 2
                and geo.width == client_geo.width + 4
                and geo.height == client_geo.height + 4
            ):
                border_matches.append(child.id)

        assert len(border_matches) == 1, "tiled client should retain one shaped border companion"
    finally:
        win.kill()
        time.sleep(0.2)


def test_toggle_floating_reparents_and_restores_root_parent(xd):
    helpers.ipc_request("view", mask=4)
    time.sleep(0.2)

    win = xd.new_window(title="test-toggle-floating-frame", size=(400, 300))
    xd.wait_for_layout()

    try:
        root = win._display.screen().root
        assert _parent_id(win) == root.id
        assert _frame_extents(win) == [0, 0, 0, 0]

        xd.keyboard.press("super+ctrl+space")
        xd.wait_for_layout()
        expect(win).to_be_reparented()
        assert _frame_extents(win) == [0, 0, TITLEBAR_HEIGHT, 0]

        xd.keyboard.press("super+ctrl+space")
        xd.wait_for_layout()
        assert _parent_id(win) == root.id
        assert win.frame.id == win.id
        assert _frame_extents(win) == [0, 0, 0, 0]
    finally:
        win.kill()
        time.sleep(0.2)


def test_fullscreen_temporarily_removes_floating_frame(xd):
    helpers.ipc_request("view", mask=8)
    time.sleep(0.2)

    win = xd.new_window(title="test-fullscreen-frame", size=(400, 300), type="dialog")
    xd.wait_for_layout()

    try:
        root = win._display.screen().root
        expect(win).to_be_reparented()

        win.set_fullscreen(True)
        xd.wait_for_layout()
        assert _parent_id(win) == root.id
        assert win.frame.id == win.id
        assert _frame_extents(win) == [0, 0, 0, 0]

        win.set_fullscreen(False)
        xd.wait_for_layout()
        expect(win).to_be_reparented()
        assert _frame_extents(win) == [0, 0, TITLEBAR_HEIGHT, 0]
    finally:
        if win.is_fullscreen:
            win.set_fullscreen(False)
            xd.wait_for_layout()
        win.kill()
        time.sleep(0.2)


def test_titlebar_is_repainted_during_super_resize(xd):
    helpers.ipc_request("view", mask=16)
    time.sleep(0.2)

    win = xd.new_window(
        title="test-live-resize-titlebar", size=(400, 300), position=(100, 100), type="dialog"
    )
    xd.wait_for_layout()

    try:
        geo = win.geometry
        sx = geo.x + geo.width * 3 // 4
        sy = geo.y + geo.height * 3 // 4

        with xd.keyboard.held("super"):
            xd.mouse.move(sx, sy)
            xd.mouse.down(3)
            try:
                time.sleep(0.05)
                xd.mouse.move(geo.x + geo.width + 100, geo.y + geo.height + 80)
                time.sleep(0.1)

                frame_geo = win.frame.geometry
                assert frame_geo.width > geo.width
                image = xd.screenshot()
                pixel = image.getpixel((frame_geo.x + frame_geo.width - 10, frame_geo.y + 5))[:3]
                assert pixel in {(0x24, 0x28, 0x3B), (0x2A, 0x2E, 0x45)}, (
                    f"titlebar should remain painted during resize, got pixel={pixel}"
                )
            finally:
                xd.mouse.up(3)
    finally:
        win.kill()
        time.sleep(0.2)


def test_super_resize_from_titlebar(xd):
    helpers.ipc_request("view", mask=32)
    time.sleep(0.2)

    win = xd.new_window(
        title="test-titlebar-super-resize", size=(400, 300), position=(100, 100), type="dialog"
    )
    xd.wait_for_layout()

    try:
        geo = win.geometry
        frame_geo = win.frame.geometry
        sx = frame_geo.x + frame_geo.width // 2
        sy = frame_geo.y + TITLEBAR_HEIGHT // 2
        ex = geo.x + geo.width + 100
        ey = geo.y + geo.height + 80

        with xd.keyboard.held("super"):
            xd.mouse.drag(sx, sy, ex, ey, steps=15, step_delay=0.015, button=3)

        xd.wait_for_layout()

        geo_after = win.geometry
        assert geo_after.width > geo.width, (
            f"Width should increase after Super+Button3 resize from titlebar: "
            f"before={geo.width}, after={geo_after.width}"
        )
        assert geo_after.height > geo.height, (
            f"Height should increase after Super+Button3 resize from titlebar: "
            f"before={geo.height}, after={geo_after.height}"
        )
    finally:
        win.kill()
        time.sleep(0.2)


def test_super_move_from_titlebar(xd):
    helpers.ipc_request("view", mask=64)
    time.sleep(0.2)

    win = xd.new_window(
        title="test-titlebar-super-move", size=(400, 300), position=(100, 100), type="dialog"
    )
    xd.wait_for_layout()

    try:
        geo = win.geometry
        frame_geo = win.frame.geometry
        sx = frame_geo.x + frame_geo.width // 2
        sy = frame_geo.y + TITLEBAR_HEIGHT // 2

        with xd.keyboard.held("super"):
            xd.mouse.drag(sx, sy, sx + 100, sy + 80, steps=15, step_delay=0.015)

        xd.wait_for_layout()

        geo_after = win.geometry
        assert abs((geo_after.x - geo.x) - 100) < 30, (
            f"Horizontal displacement off after Super+Button1 titlebar move: "
            f"got dx={geo_after.x - geo.x}, expected ~100"
        )
        assert abs((geo_after.y - geo.y) - 80) < 30, (
            f"Vertical displacement off after Super+Button1 titlebar move: "
            f"got dy={geo_after.y - geo.y}, expected ~80"
        )
    finally:
        win.kill()
        time.sleep(0.2)
