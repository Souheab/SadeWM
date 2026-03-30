#!/usr/bin/env bash
# Validate Quickshell config without a display server.
# Usage: ./scripts/check.sh [path-to-config-dir]
# Exits 0 if the config loads successfully, non-zero on errors.

set -euo pipefail

config_dir="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
timeout_sec="${QS_CHECK_TIMEOUT:-5}"

export QT_QPA_PLATFORM=offscreen
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/qs-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"

# Run quickshell with a timeout, capturing output for analysis.
set +e
output=$(timeout "$timeout_sec" quickshell -p "$config_dir" 2>&1)
exit_code=$?
set -e

echo "$output"

# timeout(1) returns 124 when the process was killed by the timeout,
# meaning quickshell ran without error for the full duration — success.
if [[ $exit_code -eq 124 ]]; then
  echo "Config OK"
  exit 0
fi

# "No PanelWindow backend loaded" is expected in offscreen mode (no compositor).
# This error cascades upward ("Type Bar unavailable" etc.) but means QML
# parsing/type-checking of the actual config passed — treat as success.
if echo "$output" | grep -q "No PanelWindow backend loaded" \
   && ! echo "$output" | grep -qE "Cannot assign|is not a type"; then
  echo "Config OK (no compositor — panel backend unavailable, but config parsed successfully)"
  exit 0
fi

exit "$exit_code"
