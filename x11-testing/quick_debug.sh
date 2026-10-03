#!/bin/bash
# Quick debug: start Xvfb+wm, spawn windows, inspect positions
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cargo build --manifest-path "$REPO_ROOT/wm/Cargo.toml" --locked

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
"$REPO_ROOT/wm/target/debug/sadewm" -d &
WM=$!
sleep 2

xeyes &
XE1=$!
sleep 0.5
xeyes &
XE2=$!
sleep 1

python3 "$REPO_ROOT/x11-testing/debug_windows.py" 2>&1


kill $XE1 $XE2 $WM $XVFB 2>/dev/null || true
wait 2>/dev/null
