#!/usr/bin/env bash
# Run the Rust WM, picom and SadeShell in a nested X11 desktop.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$REPO_ROOT/wm/scripts/run_xephyr_session.sh"

for arg in "$@"; do
    if [[ "$arg" == --help || "$arg" == -h ]]; then
        cat <<EOF
Usage: $(basename "$0") [options]

Build and run sadewm-rs, picom and SadeShell inside Xephyr, using a private
D-Bus session and default WM settings (no user startup script).
Run from 'nix develop' inside an existing X11 session.

Options:
  --display DISPLAY   Nested X display (default: :7)
  --screen GEOMETRY   Xephyr geometry/depth (default: 1280x800x24)
  --no-overlay        Do not open the window picker automatically
  --no-test-windows   Do not launch test terminals
  --skip-build        Reuse the Rust release binary and Nix shell output
  -h, --help          Show this help

Close with Ctrl+C in the launching terminal. Logs are retained under /tmp.
EOF
        exit 0
    fi
done

if ! command -v dbus-run-session >/dev/null 2>&1; then
    echo "ERROR: dbus-run-session is unavailable; run from 'nix develop'." >&2
    exit 1
fi

exec dbus-run-session -- "$RUNNER" "$@" --backend rust --no-config
