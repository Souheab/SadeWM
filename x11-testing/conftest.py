"""
conftest.py — pytest fixtures for sadewm x11-testing suite.

Connects to the running X display (set by run_tests.sh or $DISPLAY).
Does NOT start Xvfb or sadewm — those are started externally by run_tests.sh.
"""

import os
import sys

import pytest

# Ensure helpers.py (IPC, WM log helpers) is importable from within this dir
sys.path.insert(0, os.path.dirname(__file__))

from xdrive import XDrive


@pytest.fixture(scope="session")
def xd():
    """Session-scoped XDrive connected to the running sadewm display.

    The display is read from $DISPLAY (set to :98 by run_tests.sh).
    No WM is started — sadewm must already be running.
    """
    display = os.environ.get("DISPLAY", ":98")
    with XDrive(display=display) as xd:
        yield xd
