"""
conftest.py — pytest fixtures for sadewm x11-testing suite.

When SADEWM_BIN is set (e.g. by run_tests.sh), this fixture manages the
full headless lifecycle: starts Xvfb via xdrive's VirtualDisplay, launches
sadewm, runs the tests, then tears everything down.

Without SADEWM_BIN the fixture connects to whatever $DISPLAY is already set,
so you can run tests against a manually-started sadewm instance.
"""

import os
import subprocess
import sys
import time

import pytest

# Ensure helpers.py (IPC, WM log helpers) is importable from within this dir
sys.path.insert(0, os.path.dirname(__file__))

from xdrive import XDrive
from xdrive.display import VirtualDisplay


@pytest.fixture(scope="session")
def xd():
    """Session-scoped XDrive instance with Xvfb + sadewm lifecycle management.

    Headless mode (SADEWM_BIN set):
        Starts a VirtualDisplay via xdrive, launches sadewm pointing at it,
        connects XDrive, yields, then tears everything down in reverse order.
        WM output is written to SADEWM_LOG (default /tmp/sadewm_headless.log).

    Attached mode (SADEWM_BIN not set):
        Connects XDrive to the display named by $DISPLAY (default :98).
        Xvfb and sadewm must already be running externally.
    """
    wm_bin = os.environ.get("SADEWM_BIN")

    if not wm_bin:
        display = os.environ.get("DISPLAY", ":98")
        print(f"\n[conftest] mode=attached  display={display}  (no SADEWM_BIN set)")
        with XDrive(display=display) as xd:
            yield xd
        return

    log_path = os.environ.get("SADEWM_LOG", "/tmp/sadewm_headless.log")

    vd = VirtualDisplay(width=1280, height=800)
    vd.start()
    print(f"\n[conftest] mode=headless  display={vd.name}  bin={wm_bin}  log={log_path}")

    env = os.environ.copy()
    env["DISPLAY"] = vd.name
    os.environ["DISPLAY"] = vd.name  # also update current process so helpers.get_socket_path() resolves correctly

    log_fh = open(log_path, "w")
    wm_proc = subprocess.Popen(
        [wm_bin, "-d"],
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    # Give the WM time to initialise and grab the root window
    time.sleep(1.0)

    try:
        with XDrive(display=vd.name) as xd:
            yield xd
    finally:
        wm_proc.terminate()
        try:
            wm_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            wm_proc.kill()
            wm_proc.wait()
        log_fh.close()
        vd.stop()
