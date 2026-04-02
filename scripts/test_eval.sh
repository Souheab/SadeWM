#!/usr/bin/env bash
# Evaluate a QML expression inside a headless Quickshell instance.
# Uses xvfb-run so PanelWindow loads correctly without a real display.
# Requires: xvfb, libxcb-cursor0  (apt install xvfb libxcb-cursor0)
#
# Usage: ./scripts/test_eval.sh "<expression>"
# Example: ./scripts/test_eval.sh "1+1"

set -euo pipefail

CODE="${1:-2 + 2}"

# Create a temporary runtime directory to avoid conflicts with any running instance
export XDG_RUNTIME_DIR=$(mktemp -d -t qs-test-XXXXXX)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_DIR/test_shell.qml"

# Force software rendering — Xvfb has no GPU/GLX support
export QT_QUICK_BACKEND=software
export LIBGL_ALWAYS_SOFTWARE=1

echo "Starting Quickshell in the background..."
xvfb-run --auto-servernum quickshell -p "$CONFIG" > "$XDG_RUNTIME_DIR/qs.log" 2>&1 &
QS_PID=$!

trap 'kill $QS_PID 2>/dev/null; sleep 0.2; rm -rf -- "$XDG_RUNTIME_DIR" 2>/dev/null; true' EXIT

echo "Waiting for Quickshell to initialize..."
for i in {1..20}; do
    if ! kill -0 $QS_PID 2>/dev/null; then
        break
    fi
    if [ -d "$XDG_RUNTIME_DIR/quickshell" ]; then
        sleep 1
        break
    fi
    sleep 0.5
done

if kill -0 $QS_PID 2>/dev/null; then
    echo "Quickshell is running (PID $QS_PID)."
    echo "Evaluating: $CODE"
    echo "--------------------------------------------------------"
    quickshell -p "$CONFIG" ipc call debug evaluate "$CODE"
    echo "--------------------------------------------------------"
else
    echo "Error: Quickshell failed to start or crashed. Logs:"
    echo "--------------------------------------------------------"
    cat "$XDG_RUNTIME_DIR/qs.log"
    echo "--------------------------------------------------------"
    exit 1
fi
