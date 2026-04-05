#!/bin/bash
# test_sadewm_headless.sh — run sadewm-go inside Xvfb (fully headless) for smoke-testing
# Usage: ./scripts/test_sadewm_headless.sh [-r] [-d] [-t <seconds>]
#   -r   recompile before running
#   -d   enable sadewm debug logging
#   -t   how long to let sadewm run before declaring success (default: 5)
set -euo pipefail

DISPLAY_NUM=":97"
SCREEN="1280x800x24"
RECOMPILE=false
DEBUG=false
RUN_SECS=5
LOG_FILE="/tmp/sadewm_headless.log"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r) RECOMPILE=true ;;
        -d) DEBUG=true ;;
        -t) RUN_SECS="$2"; shift ;;
        *)  echo "Usage: $0 [-r] [-d] [-t seconds]"; exit 1 ;;
    esac
    shift
done

cd "$(dirname "$0")/.."

# ── install Xvfb if missing ───────────────────────────────────────────────────
if ! command -v Xvfb &>/dev/null; then
    echo "==> Xvfb not found — installing xvfb..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y xvfb
    elif command -v nix-env &>/dev/null; then
        nix-env -iA nixpkgs.xorg.xorgserver
    else
        echo "ERROR: cannot install Xvfb — install it manually." >&2
        exit 1
    fi
fi

# ── (re)compile ───────────────────────────────────────────────────────────────
if $RECOMPILE; then
    echo "==> Building sadewm (Go)..."
    make clean && make
fi

if [[ ! -f ./sadewm ]]; then
    echo "ERROR: ./sadewm binary not found. Run with -r to compile first." >&2
    exit 1
fi

# ── kill any stale Xvfb on our display ───────────────────────────────────────
pkill -f "Xvfb $DISPLAY_NUM" 2>/dev/null || true
sleep 0.3

# ── start Xvfb ────────────────────────────────────────────────────────────────
XVFB_PID=""
WM_PID=""

cleanup() {
    echo "==> Cleaning up..."
    [[ -n "$XVFB_PID" ]] && kill "$XVFB_PID" 2>/dev/null || true
    [[ -n "$WM_PID"   ]] && kill "$WM_PID"   2>/dev/null || true
}
trap cleanup EXIT

echo "==> Starting Xvfb on $DISPLAY_NUM ($SCREEN)..."
Xvfb "$DISPLAY_NUM" -screen 0 "$SCREEN" -ac &
XVFB_PID=$!

# Wait for Xvfb to be ready
for i in $(seq 1 20); do
    if DISPLAY="$DISPLAY_NUM" xdpyinfo &>/dev/null 2>&1; then
        break
    fi
    sleep 0.2
    if [[ $i -eq 20 ]]; then
        echo "ERROR: Xvfb did not become ready in time." >&2
        exit 1
    fi
done

export DISPLAY="$DISPLAY_NUM"

# ── launch sadewm ─────────────────────────────────────────────────────────────
WM_ARGS=()
$DEBUG && WM_ARGS+=(-d)

echo "==> Starting sadewm (will run for ${RUN_SECS}s)..."
./sadewm "${WM_ARGS[@]}" >"$LOG_FILE" 2>&1 &
WM_PID=$!

# Wait up to RUN_SECS for sadewm to either crash or keep running
for i in $(seq 1 "$((RUN_SECS * 10))"); do
    if ! kill -0 "$WM_PID" 2>/dev/null; then
        # Process exited — fetch exit code
        wait "$WM_PID" || EXIT_CODE=$?
        echo "==> sadewm exited unexpectedly after $((i / 10))s (exit code: ${EXIT_CODE:-?})."
        echo "--- log ---"
        cat "$LOG_FILE"
        echo "-----------"
        exit 1
    fi
    sleep 0.1
done

echo "==> sadewm ran for ${RUN_SECS}s without crashing. PASS."
if [[ -s "$LOG_FILE" ]]; then
    echo "--- sadewm log ---"
    cat "$LOG_FILE"
    echo "------------------"
fi
