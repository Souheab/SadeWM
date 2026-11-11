"""Directional (vim-style) focus and swap: super+h/j/k/l and super+shift+h/j/k/l.

SADEWM_TEST_BINARY=/path/sadewm \
  PYTHONPATH=xdrive python -m pytest wm/tests/test_directional_focus.py -q
"""
import pytest

from test_regression import WM, card, desktop, request

pytestmark = pytest.mark.skipif(not WM, reason="WM binary required")


def active(xd):
    return card(xd, xd._xdisplay.screen().root, "_NET_ACTIVE_WINDOW")[0]


def press(xd, keys):
    xd.keyboard.press(keys)
    xd.wait_for_layout()


def focus(xd, sock, win):
    request(sock, "focus_window", win_id=win.id)
    xd.wait_for_layout()
    assert active(xd) == win.id


def tile_three(xd):
    """Master on the left, two stacked windows on the right: M | top / bottom."""
    windows = [xd.new_window(title=f"w{i}", size=(400, 240)) for i in range(3)]
    xd.wait_for_layout()
    master = min(windows, key=lambda w: w.geometry.x)
    top, bottom = sorted((w for w in windows if w is not master), key=lambda w: w.geometry.y)
    assert top.geometry.x == bottom.geometry.x > master.geometry.x
    return master, top, bottom


def test_jk_move_vertically_within_a_column(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        master, top, bottom = tile_three(xd)
        focus(xd, sock, top)
        press(xd, "super+j")
        assert active(xd) == bottom.id
        press(xd, "super+j")  # nothing further down: stay put
        assert active(xd) == bottom.id
        press(xd, "super+k")
        assert active(xd) == top.id
        press(xd, "super+k")  # nothing above: stay put
        assert active(xd) == top.id


def test_j_never_jumps_sideways(tmp_path):
    # The master spans the full height, so there is no window below it.
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        master, top, bottom = tile_three(xd)
        focus(xd, sock, master)
        press(xd, "super+j")
        assert active(xd) == master.id
        press(xd, "super+k")
        assert active(xd) == master.id


def test_hl_move_between_columns_and_return_to_last_window(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        master, top, bottom = tile_three(xd)
        focus(xd, sock, bottom)
        press(xd, "super+h")
        assert active(xd) == master.id
        press(xd, "super+l")  # back to where we came from, not the top window
        assert active(xd) == bottom.id
        press(xd, "super+l")  # nothing to the right
        assert active(xd) == bottom.id


def test_jk_survive_runtime_gap_changes(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        master, top, bottom = tile_three(xd)
        for keys in ("super+equal", "super+equal", "super+equal"):
            press(xd, keys)
        focus(xd, sock, top)
        press(xd, "super+j")
        assert active(xd) == bottom.id
        press(xd, "super+k")
        assert active(xd) == top.id
        press(xd, "super+minus")
        for _ in range(12):
            press(xd, "super+minus")  # gaps clamp at 0
        press(xd, "super+j")
        assert active(xd) == bottom.id


def test_jk_with_two_masters(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        windows = [xd.new_window(title=f"w{i}", size=(400, 240)) for i in range(3)]
        xd.wait_for_layout()
        press(xd, "alt+k")  # nmaster 1 -> 2
        left_x = min(w.geometry.x for w in windows)
        upper, lower = sorted((w for w in windows if w.geometry.x == left_x), key=lambda w: w.geometry.y)
        (stack,) = [w for w in windows if w.geometry.x != left_x]
        focus(xd, sock, upper)
        press(xd, "super+j")
        assert active(xd) == lower.id
        press(xd, "super+k")
        assert active(xd) == upper.id
        press(xd, "super+l")
        assert active(xd) == stack.id
        press(xd, "super+h")  # returns to the master we left
        assert active(xd) == upper.id


def test_directions_in_floating_layout(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        press(xd, "super+shift+f")  # floating layout
        upper_left = xd.new_window(title="ul", size=(300, 200), position=(60, 120))
        lower_left = xd.new_window(title="ll", size=(300, 200), position=(80, 480))
        right = xd.new_window(title="r", size=(300, 200), position=(800, 150))
        xd.wait_for_layout()
        focus(xd, sock, upper_left)
        press(xd, "super+j")
        assert active(xd) == lower_left.id
        press(xd, "super+k")
        assert active(xd) == upper_left.id
        press(xd, "super+l")
        assert active(xd) == right.id
        press(xd, "super+h")
        assert active(xd) == upper_left.id


def test_swap_keeps_focus_on_moved_window_under_pointer(tmp_path):
    with desktop(WM, tmp_path) as (xd, sock, process, env):
        master, top, bottom = tile_three(xd)
        focus(xd, sock, top)
        g = top.geometry
        xd.mouse.move(g.x + g.width // 2, g.y + g.height // 2)
        xd.wait_for_layout()
        top_slot, bottom_slot = top.geometry, bottom.geometry
        press(xd, "super+shift+j")
        assert top.geometry == bottom_slot and bottom.geometry == top_slot
        # The pointer now rests over the other window; focus must not follow it.
        assert active(xd) == top.id
        press(xd, "super+shift+k")
        assert top.geometry == top_slot
        assert active(xd) == top.id
