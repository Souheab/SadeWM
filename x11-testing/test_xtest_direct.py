#!/usr/bin/env python3
"""Test using python-xlib XTest extension directly for more reliable event injection."""
import os, sys, time
os.environ.setdefault("DISPLAY", ":42")

from Xlib import display, X
from Xlib.ext import xtest

LOG = os.path.expanduser("~/.local/share/sadewm/sadewm.log")
try:
    log_start = os.path.getsize(LOG)
except FileNotFoundError:
    log_start = 0

d = display.Display()
r = d.screen().root

print("=== Test: python-xlib XTest for Super+Drag ===")

# First move to a known position inside the window
xtest.fake_input(d, X.MotionNotify, x=200, y=400, root=r)
d.sync()
time.sleep(0.2)

# Verify pointer is in window
q = r.query_pointer()
print(f"Pointer: ({q.root_x},{q.root_y}), child=0x{q.child.id if q.child else 0:x}")

# Send KeyPress for Super_L (keycode for Super on most systems)
# Find keycodes for Super_L
from Xlib import XK
super_keycode = d.keysym_to_keycode(XK.XK_Super_L)
print(f"Super_L keycode: {super_keycode}")

# KeyPress Super_L
xtest.fake_input(d, X.KeyPress, detail=super_keycode)
d.sync()
time.sleep(0.1)

# ButtonPress 1
xtest.fake_input(d, X.ButtonPress, detail=1)
d.sync()
time.sleep(0.3)

# MotionNotify to (700, 400)
xtest.fake_input(d, X.MotionNotify, x=700, y=400, root=r)
d.sync()
time.sleep(0.2)

# ButtonRelease 1
print("Sending ButtonRelease...")
xtest.fake_input(d, X.ButtonRelease, detail=1)
d.sync()
time.sleep(0.1)

# KeyRelease Super_L
xtest.fake_input(d, X.KeyRelease, detail=super_keycode)
d.sync()
time.sleep(0.5)

# Read WM log
try:
    with open(LOG) as f:
        f.seek(log_start)
        new_log = f.read()
except FileNotFoundError:
    new_log = "(log not found)"

print("\n=== WM log entries ===")
for line in new_log.strip().splitlines():
    print(f"  {line}")

has_motion = "MoveMouse: MotionNotify" in new_log
has_release = "ButtonRelease" in new_log
has_pump_release = "eventpump: got xproto.ButtonReleaseEvent" in new_log
print(f"\nMoveMouse got MotionNotify: {has_motion}")
print(f"ButtonRelease event logged: {has_release}")
print(f"Event pump saw ButtonRelease: {has_pump_release}")

d.close()
