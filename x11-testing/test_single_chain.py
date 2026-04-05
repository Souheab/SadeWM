#!/usr/bin/env python3
"""Test drag using a single xdotool chain to avoid multi-connection issues."""
import os, sys, time, subprocess
os.environ.setdefault("DISPLAY", ":42")

LOG = os.path.expanduser("~/.local/share/sadewm/sadewm.log")
try:
    log_start = os.path.getsize(LOG)
except FileNotFoundError:
    log_start = 0

print("=== Test: Single xdotool chain for Super+Drag ===")

# Move to center of first window
subprocess.run(["xdotool", "mousemove", "200", "400"], timeout=3)
time.sleep(0.2)

# Single xdotool chain: keydown super, mousedown 1, delay, mousemove, delay, mouseup 1, keyup super
# Using xdotool's chained commands
result = subprocess.run(
    ["xdotool",
     "keydown", "super",
     "mousedown", "1",
     "sleep", "0.2",
     "mousemove", "700", "400",
     "sleep", "0.2",
     "mouseup", "1",
     "keyup", "super"],
    capture_output=True, text=True, timeout=15
)
print(f"xdotool exit={result.returncode}")
if result.stderr:
    print(f"xdotool stderr: {result.stderr.strip()}")

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
