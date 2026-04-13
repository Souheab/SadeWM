#!/bin/bash
# test_sadewm.sh — run sadewm inside a Xephyr nested display
set -euo pipefail

DISPLAY_NUM=":7"
SCREEN="1280x800"
RECOMPILE=false
DEBUG=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r) RECOMPILE=true ;;
        -d) DEBUG=true ;;
        *)  echo "Usage: $0 [-r] [-d]"; exit 1 ;;
    esac
    shift
done

cd "$(dirname "$0")/.."

if $RECOMPILE; then
    echo "==> Building sadewm (Go)..."
    make clean && make
fi

if [[ ! -f ./sadewm ]]; then
    echo "Error: ./sadewm binary not found. Run with -r to compile first."
    exit 1
fi

# Kill any existing Xephyr on this display
if xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
    echo "==> Killing existing Xephyr on $DISPLAY_NUM..."
    pkill -f "Xephyr.*$DISPLAY_NUM" 2>/dev/null || true
    sleep 0.5
fi

echo "==> Starting Xephyr on $DISPLAY_NUM ($SCREEN)..."
Xephyr "$DISPLAY_NUM" -screen "$SCREEN" -ac &
XEPHYR_PID=$!
sleep 1

cleanup() {
    echo "==> Cleaning up..."
    kill $XEPHYR_PID 2>/dev/null || true
}
trap cleanup EXIT

export DISPLAY="$DISPLAY_NUM"

if $DEBUG; then
    echo "==> Starting sadewm under dlv debugger..."
    dlv exec ./sadewm -- -d
else
    echo "==> Starting sadewm..."
    ./sadewm -d
fi
