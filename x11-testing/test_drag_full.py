#!/usr/bin/env python3
"""Test full Super+drag sequence - verify MotionNotify and ButtonRelease."""
import os, sys, time, subprocess
os.environ.setdefault("DISPLAY", ":42")

LOG = os.path.expanduser("~/.local/share/sadewm/sadewm.log")
try:
    log_start = os.path.getsize(LOG)
except FileNotFoundError:
    log_start = 0

print("=== Testing full Super+Drag ===")

# Move to center of first window
subprocess.run(["xdotool", "mousemove", "200", "400"], timeout=3)
time.sleep(0.2)

# Super key down
subprocess.run(["xdotool", "keydown", "super"], timeout=3)
time.sleep(0.1)

# Mouse button 1 down
subprocess.run(["xdotool", "mousedown", "1"], timeout=3)
time.sleep(0.3)

# Move mouse to the right (into slave area)
for i in range(5):
    nx = 200 + (i + 1) * 100
    subprocess.run(["xdotool", "mousemove", str(nx), "400"], timeout=3)
    time.sleep(0.05)

time.sleep(0.2)

# Mouse button 1 up
subprocess.run(["xdotool", "mouseup", "1"], timeout=3)
time.sleep(0.1)

# Super key up
subprocess.run(["xdotool", "keyup", "super"], timeout=3)
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

has_motion = "MotionNotify" in new_log
has_release = "ButtonRelease" in new_log
has_grab = "GrabPointer status=0" in new_log
print(f"\nGrabPointer succeeded: {has_grab}")
print(f"MotionNotify received: {has_motion}")
print(f"ButtonRelease received: {has_release}")

# Check IPC state
import json, socket

def ipc_get():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(f"/tmp/sadewm-42.sock")
    sock.sendall(b'{"cmd":"get_state"}')
    sock.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    sock.close()
    return json.loads(data)

try:
    state = ipc_get()
    print(f"\nIPC state after drag: {json.dumps(state, indent=2)}")
except Exception as e:
    print(f"\nIPC error: {e}")
