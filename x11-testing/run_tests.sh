#!/bin/bash
# run_tests.sh — Start Xvfb + sadewm, run the X11 test suite, collect results.
# Usage: ./x11-testing/run_tests.sh [-d] [-t test_file.py]
#   -d   enable sadewm debug logging
#   -t   run only the specified test file (default: all tests)
set -euo pipefail

DISPLAY_NUM=":98"
SCREEN="1280x800x24"
DEBUG=true      # default: debug on so we see WM logs
TEST_FILE=""
LOG_FILE="/tmp/sadewm_headless.log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d) DEBUG=true ;;
        -t) TEST_FILE="$2"; shift ;;
        *)  echo "Usage: $0 [-d] [-t test_file.py]"; exit 1 ;;
    esac
    shift
done

# ── Preflight checks ─────────────────────────────────────────────────────────
for tool in Xvfb xdotool xeyes python3; do
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: $tool not found. Install it first." >&2
        exit 1
    fi
done

python3 -c "import Xlib" 2>/dev/null || {
    echo "ERROR: python3-xlib not installed." >&2
    exit 1
}

# ── Build sadewm-go ──────────────────────────────────────────────────────────
echo "==> Building sadewm-go..."
cd "$REPO_ROOT/wm-go"
make -s 2>&1
WM_BIN="$REPO_ROOT/wm-go/sadewm"
if [[ ! -x "$WM_BIN" ]]; then
    echo "ERROR: sadewm binary not found at $WM_BIN" >&2
    exit 1
fi

# ── Cleanup ───────────────────────────────────────────────────────────────────
pkill -f "Xvfb $DISPLAY_NUM" 2>/dev/null || true
sleep 0.3

XVFB_PID=""
WM_PID=""

cleanup() {
    echo "==> Cleaning up..."
    [[ -n "$WM_PID"   ]] && kill "$WM_PID"   2>/dev/null || true
    sleep 0.2
    [[ -n "$XVFB_PID" ]] && kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── Start Xvfb ───────────────────────────────────────────────────────────────
echo "==> Starting Xvfb on $DISPLAY_NUM ($SCREEN)..."
Xvfb "$DISPLAY_NUM" -screen 0 "$SCREEN" -ac 2>/dev/null &
XVFB_PID=$!

for i in $(seq 1 30); do
    if DISPLAY="$DISPLAY_NUM" xdpyinfo &>/dev/null 2>&1; then
        break
    fi
    sleep 0.2
    if [[ $i -eq 30 ]]; then
        echo "ERROR: Xvfb did not become ready." >&2
        exit 1
    fi
done

export DISPLAY="$DISPLAY_NUM"

# ── Start sadewm ─────────────────────────────────────────────────────────────
WM_ARGS=()
$DEBUG && WM_ARGS+=(-d)

echo "==> Starting sadewm (debug=$DEBUG)..."
: > "$LOG_FILE"
"$WM_BIN" "${WM_ARGS[@]}" >>"$LOG_FILE" 2>&1 &
WM_PID=$!
sleep 1

if ! kill -0 "$WM_PID" 2>/dev/null; then
    echo "ERROR: sadewm crashed on startup."
    cat "$LOG_FILE"
    exit 1
fi
echo "==> sadewm running (PID=$WM_PID)"

# ── Run tests ─────────────────────────────────────────────────────────────────
cd "$REPO_ROOT"
EXIT_CODE=0

if [[ -n "$TEST_FILE" ]]; then
    echo "==> Running test: $TEST_FILE"
    python3 "$TEST_FILE" || EXIT_CODE=$?
else
    echo "==> Running all tests in $SCRIPT_DIR/"
    for f in "$SCRIPT_DIR"/test_*.py; do
        [[ -f "$f" ]] || continue
        echo ""
        echo "━━━ $(basename "$f") ━━━"
        python3 "$f" || EXIT_CODE=$?
    done
fi

# ── Dump WM log on failure ───────────────────────────────────────────────────
if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "==> TESTS FAILED. Full sadewm log:"
    echo "--- log ---"
    cat "$LOG_FILE"
    echo "-----------"
fi

exit $EXIT_CODE
