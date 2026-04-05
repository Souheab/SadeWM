#!/usr/bin/env python3
"""Test if Super+click is received on the correct window."""
import os, sys, time, subprocess
os.environ.setdefault("DISPLAY", ":42")

# Clear the WM log
LOG = os.path.expanduser("~/.local/share/sadewm/sadewm.log")
try:
    log_start = os.path.getsize(LOG)
except FileNotFoundError:
    log_start = 0

# Move to center of first window at (200, 400) — well inside 0x40000a
subprocess.run(["xdotool", "mousemove", "200", "400"], timeout=3)
time.sleep(0.1)

# Verify pointer is in the right window
from Xlib import display
d = display.Display()
r = d.screen().root
q = r.query_pointer()
print(f"Before click: pointer=({q.root_x},{q.root_y}) child=0x{q.child.id if q.child else 0:x}")
d.close()

# Now do Super+Click
subprocess.run(["xdotool", "keydown", "super"], timeout=3)
time.sleep(0.05)
subprocess.run(["xdotool", "mousedown", "1"], timeout=3)
time.sleep(0.3)
subprocess.run(["xdotool", "mouseup", "1"], timeout=3)
time.sleep(0.05)
subprocess.run(["xdotool", "keyup", "super"], timeout=3)
time.sleep(0.5)

# Read new WM log entries
try:
    with open(LOG) as f:
        f.seek(log_start)
        new_log = f.read()
except FileNotFoundError:
    new_log = "(log not found)"

print("\n=== New WM log entries ===")
for line in new_log.strip().splitlines():
    print(f"  {line}")

if "buttonpress:" not in new_log:
    print("\n!!! NO buttonpress in log - event not received by WM")
elif "no client found" in new_log:
    print("\n!!! ButtonPress arrived at root window, not at client window")
    print("    -> Passive grabs on client windows are NOT activating")
elif "matched action" in new_log:
    print("\n=== ButtonPress received and action matched ===")
