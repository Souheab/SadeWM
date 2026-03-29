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

# Run quickshell with a timeout. If it survives the timeout, the config loaded
# successfully (exit 0). If it exits before the timeout, it hit an error.
timeout "$timeout_sec" quickshell -p "$config_dir" 2>&1
exit_code=$?

# timeout(1) returns 124 when the process was killed by the timeout,
# meaning quickshell ran without error for the full duration — success.
if [[ $exit_code -eq 124 ]]; then
  echo "Config OK"
  exit 0
fi

exit "$exit_code"
