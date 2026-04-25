#!/usr/bin/env bash
# run_tests.sh — Build sadewm and run the X11 test suite.
# Xvfb and sadewm are started/stopped by conftest.py via xdrive.
#
# Usage: ./x11-testing/run_tests.sh [-t test_file.py]
#   -t   run only the specified test file (default: all tests)
set -euo pipefail

TEST_FILE=""
LOG_FILE="/tmp/sadewm_headless.log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t) TEST_FILE="$2"; shift ;;
        *)  echo "Usage: $0 [-t test_file.py]"; exit 1 ;;
    esac
    shift
done

# ── Preflight checks ─────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found." >&2
    exit 1
fi
python3 -c "import Xlib" 2>/dev/null || {
    echo "ERROR: python3-xlib not installed." >&2
    exit 1
}

# ── Build sadewm ─────────────────────────────────────────────────────────────
echo "==> Building sadewm..."
cd "$REPO_ROOT/wm"
make -s 2>&1
WM_BIN="$REPO_ROOT/wm/sadewm"
if [[ ! -x "$WM_BIN" ]]; then
    echo "ERROR: sadewm binary not found at $WM_BIN" >&2
    exit 1
fi

# ── Run tests ─────────────────────────────────────────────────────────────────
cd "$REPO_ROOT"

# Ensure xdrive package is importable; pass WM binary + log path to conftest.
export PYTHONPATH="$REPO_ROOT/xdrive${PYTHONPATH:+:$PYTHONPATH}"
export SADEWM_BIN="$WM_BIN"
export SADEWM_LOG="$LOG_FILE"

EXIT_CODE=0

if [[ -n "$TEST_FILE" ]]; then
    echo "==> Running test: $TEST_FILE"
    python3 -m pytest "$TEST_FILE" -v || EXIT_CODE=$?
else
    echo "==> Running all tests in $SCRIPT_DIR/"
    python3 -m pytest "$SCRIPT_DIR" -v || EXIT_CODE=$?
fi

# ── Dump WM log on failure ───────────────────────────────────────────────────
if [[ $EXIT_CODE -ne 0 && -f "$LOG_FILE" ]]; then
    echo ""
    echo "==> TESTS FAILED. Full sadewm log:"
    echo "--- log ---"
    cat "$LOG_FILE"
    echo "-----------"
fi

exit $EXIT_CODE
