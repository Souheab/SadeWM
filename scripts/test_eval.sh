#!/usr/bin/env bash

# Use the first argument as the code to evaluate, default to "2 + 2" if empty
CODE="${1:-2 + 2}"

# Create a temporary runtime directory to avoid conflicts with any running instance
export XDG_RUNTIME_DIR=$(mktemp -d -t qs-test-XXXXXX)

# Force Qt QML to use the software renderer instead of OpenGL/GLX for headless testing
export QT_QUICK_BACKEND=software
export LIBGL_ALWAYS_SOFTWARE=1

echo "Starting Quickshell in the background..."
# Run quickshell redirecting output to a log file
quickshell -p "$(pwd)/shell.qml" > "$XDG_RUNTIME_DIR/qs.log" 2>&1 &
QS_PID=$!

# Set a trap to ensure we always clean up the background process
trap 'if kill -0 $QS_PID 2>/dev/null; then kill $QS_PID; fi' EXIT

echo "Waiting for Quickshell to initialize..."
# Poll for up to 5 seconds to see if it stays alive and creates its runtime folder
for i in {1..10}; do
    if ! kill -0 $QS_PID 2>/dev/null; then
        break
    fi
    # Wait until quickshell creates its IPC socket directory
    if [ -d "$XDG_RUNTIME_DIR/quickshell" ]; then
        sleep 1 # Give it one more second to finish loading QML components
        break
    fi
    sleep 0.5
done

# Check if the process is still running
if kill -0 $QS_PID 2>/dev/null; then
    echo "Quickshell is running successfully (PID $QS_PID)."
    echo "Evaluating: $CODE"
    echo "--------------------------------------------------------"
    python3 "$(pwd)/scripts/qsctrl" debug eval "$CODE"
    echo "--------------------------------------------------------"
else
    echo "Error: Quickshell failed to start or crashed. Here are the logs:"
    echo "--------------------------------------------------------"
    cat "$XDG_RUNTIME_DIR/qs.log"
    echo "--------------------------------------------------------"
    exit 1
fi
