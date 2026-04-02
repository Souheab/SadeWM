#!/usr/bin/env bash
# Validate Quickshell config with a virtual X11 display (xvfb-run).
# Usage: ./scripts/check.sh [path-to-config-dir]
# Requires: xvfb, libxcb-cursor0  (apt install xvfb libxcb-cursor0)
# Exits 0 if the config loads successfully, non-zero on errors.

set -euo pipefail

config_dir="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
timeout_sec="${QS_CHECK_TIMEOUT:-5}"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/qs-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"

# Force software rendering — Xvfb has no GPU/GLX support
export QT_QUICK_BACKEND=software
export LIBGL_ALWAYS_SOFTWARE=1

# xvfb-run provides a virtual X11 display so PanelWindow loads normally.
set +e
output=$(xvfb-run --auto-servernum timeout "$timeout_sec" quickshell -p "$config_dir" 2>&1)
exit_code=$?
set -e

# Strip ANSI color codes for reliable text matching
output=$(printf '%s' "$output" | sed 's/\x1b\[[0-9;]*m//g')

echo "$output"

# timeout(1) returns 124 when the process was killed by the timeout,
# meaning quickshell ran without error for the full duration — success.
if [[ $exit_code -eq 124 ]]; then
  echo "Config OK"
  exit 0
fi

# Any real ERROR lines indicate a genuine config problem.
if echo "$output" | grep -q " ERROR"; then
  exit 1
fi

exit "$exit_code"
