#!/usr/bin/env bash
# peek_log.sh — tail sadewm's live FIFO log.
#
# Usage:
#   ./wm-go/scripts/peek_log.sh              # just tail the FIFO
#   ./wm-go/scripts/peek_log.sh --restart    # kill + restart sadewm first
#
# The FIFO path is derived from $DISPLAY (matching sadewm's own logic):
#   DISPLAY=:0 → /home/<user>/.local/share/sadewm/sadewm.fifo
#
# Requirements: sadewm must be running (with or without -d flag).
# The log messages are always-on (not gated by -d) for buttonpress/GrabPointer.

set -euo pipefail

RESTART=0
for arg in "$@"; do
  [[ "$arg" == "--restart" ]] && RESTART=1
done

FIFO="${HOME}/.local/share/sadewm/sadewm.fifo"
LOGF="${HOME}/.local/share/sadewm/sadewm.log"
BINARY="${BINARY:-$(dirname "$(dirname "$0")")/sadewm}"

if [[ "$RESTART" == "1" ]]; then
  echo "==> Stopping sadewm..."
  pkill -x sadewm 2>/dev/null || true
  sleep 0.3

  if [[ ! -x "$BINARY" ]]; then
    echo "==> Building sadewm-go..."
    (cd "$(dirname "$(dirname "$0")")" && make -j"$(nproc)" 2>&1)
  fi

  echo "==> Starting sadewm (background)..."
  DISPLAY="${DISPLAY:-:0}" "$BINARY" &
  sleep 0.5
fi

if [[ ! -p "$FIFO" ]]; then
  echo "ERROR: FIFO not found at $FIFO"
  echo "       Is sadewm running?  Try: $0 --restart"
  exit 1
fi

echo "==> Tailing sadewm FIFO at $FIFO"
echo "==> (Ctrl-C to stop)"
echo "---"

# cat the FIFO — blocks until sadewm opens its end; will re-open on sadewm restart
# Filter to highlight drag-relevant lines
cat "$FIFO" | grep --line-buffered -E \
  'buttonpress|MoveMouse|ResizeMouse|GrabPointer|FATAL|ERROR|WARN' \
  --color=always
