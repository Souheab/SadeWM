"""
test_saxcomp.py — xdrive tests for the saxcomp compositor.

Tests:
  1. test_compositor_no_crash             — saxcomp starts and stays running
  2. test_window_visible_through_compositor — a new window renders non-black pixels
    3. test_root_wallpaper_renders_through_compositor — root wallpaper pixmap is drawn
    4. test_window_stays_clean_during_resizes — repeated resizes do not introduce black artifacts
"""

import os
import subprocess
import time

import pytest
from Xlib import Xatom

from xdrive import expect


# ── Fixture ───────────────────────────────────────────────────────────────────


def _find_saxcomp_bin():
    """Locate the saxcomp binary.

    Prefers the SAXCOMP_BIN environment variable, then looks for the
    workspace-local build at saxcomp/saxcomp relative to this file's
    directory.
    """
    env_bin = os.environ.get("SAXCOMP_BIN")
    if env_bin:
        return env_bin

    here = os.path.dirname(os.path.abspath(__file__))
    workspace_bin = os.path.join(here, "..", "saxcomp", "saxcomp")
    if os.path.isfile(workspace_bin):
        return os.path.abspath(workspace_bin)

    raise RuntimeError(
        "Cannot find saxcomp binary. Set SAXCOMP_BIN or build with "
        "'cd saxcomp && make' first."
    )


@pytest.fixture(scope="session")
def saxcomp_proc(xd):
    """Session-scoped fixture that starts saxcomp against the test display.

    Starts the compositor, waits 1 second for it to initialise, asserts
    it hasn't immediately crashed, then yields the process.  Terminates
    the process on teardown.
    """
    bin_path = _find_saxcomp_bin()
    display_name = xd._display_name

    env = os.environ.copy()
    env["DISPLAY"] = display_name

    proc = subprocess.Popen(
        [bin_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Give the compositor time to initialise and redirect windows.
    time.sleep(1.0)

    if proc.poll() is not None:
        out = proc.stdout.read().decode(errors="replace")
        pytest.fail(
            f"saxcomp exited immediately (rc={proc.returncode}):\n{out}"
        )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _window_region(xd, win):
    """Return a window region clamped to the visible screen."""
    geo = win.geometry
    sw = xd.screen.geometry.width
    sh = xd.screen.geometry.height
    x = max(0, geo.x)
    y = max(0, geo.y)
    w = max(1, min(geo.width, sw - x))
    h = max(1, min(geo.height, sh - y))
    return x, y, w, h


def _non_black_ratio(img):
    total = max(1, img.width * img.height)
    return sum(
        1 for r, g, b in img.getdata() if r > 10 or g > 10 or b > 10
    ) / total


def _dark_ratio(img):
    total = max(1, img.width * img.height)
    return sum(
        1 for r, g, b in img.getdata() if r < 20 and g < 20 and b < 20
    ) / total


def _average_rgb(img):
    pixels = list(img.getdata())
    total = max(1, len(pixels))
    return tuple(sum(pixel[idx] for pixel in pixels) / total for idx in range(3))


def _set_root_wallpaper(xd, pixel_value):
    """Create a full-screen pixmap and advertise it as the root wallpaper."""
    display = xd._xdisplay
    screen = display.screen()
    root = screen.root
    width = xd.screen.geometry.width
    height = xd.screen.geometry.height

    pixmap = root.create_pixmap(width, height, screen.root_depth)
    gc = pixmap.create_gc(foreground=pixel_value, background=pixel_value)
    pixmap.fill_rectangle(gc, 0, 0, width, height)

    xrootpmap_atom = display.intern_atom("_XROOTPMAP_ID")
    esetroot_atom = display.intern_atom("ESETROOT_PMAP_ID")
    root.change_property(xrootpmap_atom, Xatom.PIXMAP, 32, [pixmap.id])
    root.change_property(esetroot_atom, Xatom.PIXMAP, 32, [pixmap.id])
    display.flush()
    return pixmap


# ── Test 1: no crash ──────────────────────────────────────────────────────────


def test_compositor_no_crash(saxcomp_proc):
    """saxcomp should still be running 1 second after startup."""
    assert saxcomp_proc.poll() is None, (
        f"saxcomp crashed (rc={saxcomp_proc.poll()})"
    )


# ── Test 2: window renders through compositor ─────────────────────────────────


def test_window_visible_through_compositor(xd, saxcomp_proc):
    """A window launched after the compositor starts should show non-black pixels.

    xclock has a white background, so if the compositor is rendering
    correctly at least some pixels in the window region will be non-black.
    A fully black region means the compositor is not compositing the window.
    """
    assert saxcomp_proc.poll() is None, "saxcomp is not running"

    win = xd.launch("xclock -digital -update 1")
    try:
        xd.wait_for_layout()
        time.sleep(0.5)  # let the compositor paint the first frame

        expect(win).to_be_mapped()

        img = xd.screenshot(region=_window_region(xd, win))
        ratio = _non_black_ratio(img)

        assert ratio > 0.10, (
            f"Only {ratio:.1%} of pixels in the window region are non-black. "
            "The compositor may not be rendering window contents."
        )
    finally:
        try:
            win.kill()
        except Exception:
            pass


def test_root_wallpaper_renders_through_compositor(xd, saxcomp_proc):
    """A pixmap advertised via root wallpaper properties should be visible."""
    assert saxcomp_proc.poll() is None, "saxcomp is not running"

    screen = xd.screen.geometry
    region = (screen.width - 96, screen.height - 96, 64, 64)
    _set_root_wallpaper(xd, xd._xdisplay.screen().white_pixel)

    time.sleep(0.5)

    img = xd.screenshot(region=region)
    avg = _average_rgb(img)

    assert min(avg) > 220, (
        f"Expected the root wallpaper pixmap to render as a bright region, "
        f"but average RGB was {avg}."
    )


def test_window_stays_clean_during_resizes(xd, saxcomp_proc):
    """Repeated resizes should not leave black artifacts inside a white window."""
    assert saxcomp_proc.poll() is None, "saxcomp is not running"

    win = xd.new_window(
        title="saxcomp-resize-stability",
        size=(260, 180),
        position=(160, 120),
    )

    try:
        expect(win).to_be_mapped()

        samples = []
        for width, height in [
            (260, 180),
            (420, 280),
            (320, 220),
            (520, 340),
            (300, 210),
        ]:
            win.set_size(width, height)
            xd.wait_for_layout()
            time.sleep(0.15)

            img = xd.screenshot(region=_window_region(xd, win))
            dark_ratio = _dark_ratio(img)
            samples.append(((width, height), dark_ratio))

        worst_dark_ratio = max(ratio for _, ratio in samples)
        assert worst_dark_ratio < 0.02, (
            "Observed unexpected dark pixels while resizing a white test window: "
            f"{samples}"
        )
    finally:
        try:
            win.kill()
        except Exception:
            pass
