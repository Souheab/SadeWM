#!/bin/bash
# Quick debug: start Xvfb+wm, spawn windows, inspect positions
set -euo pipefail

DISP=":42"
pkill -f "Xvfb $DISP" 2>/dev/null || true
sleep 0.5

Xvfb $DISP -screen 0 1280x800x24 -ac &
XVFB=$!
sleep 2

if ! kill -0 $XVFB 2>/dev/null; then
    echo "ERROR: Xvfb failed to start"
    exit 1
fi

export DISPLAY=$DISP
/workspaces/sadewm/wm/sadewm -d &
WM=$!
sleep 2

xeyes &
XE1=$!
sleep 0.5
xeyes &
XE2=$!
sleep 1

python3 /workspaces/sadewm/x11-testing/debug_windows.py 2>&1

echo ""
echo "=== Testing XTest Direct ==="
python3 /workspaces/sadewm/x11-testing/test_xtest_direct.py 2>&1

kill $XE1 $XE2 $WM $XVFB 2>/dev/null || true
wait 2>/dev/null
