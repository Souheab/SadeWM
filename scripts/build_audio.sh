#!/usr/bin/env bash
# Build the pulse_monitor binary from source.
# Run this once (or after editing pulse_monitor.c) before starting the shell.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
gcc -O2 -Wall -Wextra \
    -o "$SCRIPT_DIR/pulse_monitor" \
    "$SCRIPT_DIR/pulse_monitor.c" \
    $(pkg-config --cflags --libs libpulse)
echo "Built: $SCRIPT_DIR/pulse_monitor"
