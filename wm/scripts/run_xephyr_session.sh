#!/usr/bin/env bash
# Build and run sadewm + sadeshell in an isolated, composited Xephyr session.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

NESTED_DISPLAY=":7"
SCREEN="1280x800x24"
OPEN_OVERLAY=true
START_TEST_WINDOWS=true
SKIP_BUILD=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Build sadewm and sadeshell, then run them in Xephyr with Picom's XRender
backend. By default, two test terminals are opened and the transparent
Alt+S window-search overlay is displayed.

Options:
  --display DISPLAY   Nested X display (default: :7)
  --screen GEOMETRY   Xephyr geometry/depth (default: 1280x800x24)
  --no-overlay        Do not open the window picker automatically
  --no-test-windows   Do not launch test terminals
  --skip-build        Reuse the latest Nix build outputs
  -h, --help          Show this help
EOF
}

while (($#)); do
    case "$1" in
        --display)
            [[ $# -ge 2 ]] || { echo "ERROR: --display needs a value" >&2; exit 2; }
            NESTED_DISPLAY="$2"
            shift 2
            ;;
        --screen)
            [[ $# -ge 2 ]] || { echo "ERROR: --screen needs a value" >&2; exit 2; }
            SCREEN="$2"
            shift 2
            ;;
        --no-overlay)
            OPEN_OVERLAY=false
            shift
            ;;
        --no-test-windows)
            START_TEST_WINDOWS=false
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ "$NESTED_DISPLAY" =~ ^:[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: display must look like :7 or :7.0" >&2
    exit 2
}

required_commands=(Xephyr xdpyinfo picom nix make go)
for command_name in "${required_commands[@]}"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: '$command_name' is unavailable." >&2
        echo "Run this script from a fresh 'nix develop' shell." >&2
        exit 1
    fi
done

HOST_DISPLAY="${DISPLAY:-}"
if [[ -z "$HOST_DISPLAY" ]] || ! xdpyinfo -display "$HOST_DISPLAY" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to the host X display '${HOST_DISPLAY:-<unset>}'." >&2
    echo "Run this from a terminal inside your live X11 session and preserve DISPLAY/XAUTHORITY." >&2
    exit 1
fi

if DISPLAY="$NESTED_DISPLAY" xdpyinfo >/dev/null 2>&1; then
    echo "ERROR: X display $NESTED_DISPLAY is already in use." >&2
    echo "Choose another one with --display; no existing session was stopped." >&2
    exit 1
fi

SESSION_DIR="$(mktemp -d "/tmp/sadewm-xephyr.XXXXXX")"
if [[ -n "${XDG_RUNTIME_DIR:-}" && -d "$XDG_RUNTIME_DIR" && -w "$XDG_RUNTIME_DIR" ]]; then
    RUNTIME_DIR="$XDG_RUNTIME_DIR"
else
    RUNTIME_DIR="$SESSION_DIR/runtime"
    mkdir -m 700 "$RUNTIME_DIR"
    # Avoid slow service autospawn attempts in a minimal/headless X session.
    export PULSE_SERVER="${PULSE_SERVER:-unix:$SESSION_DIR/no-pulse.sock}"
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$SESSION_DIR/no-session-bus}"
fi

declare -a CHILD_PIDS=()
XEPHYR_PID=""
WM_PID=""
PICOM_PID=""
SHELL_PID=""

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    echo
    echo "==> Stopping nested session..."
    if ((${#CHILD_PIDS[@]})); then
        kill "${CHILD_PIDS[@]}" 2>/dev/null || true
        wait "${CHILD_PIDS[@]}" 2>/dev/null || true
    fi
    echo "==> Logs retained in $SESSION_DIR"
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

build_output() {
    local package="$1"
    if "$SKIP_BUILD"; then
        nix path-info "$REPO_ROOT#$package" | tail -n 1
    else
        nix build "$REPO_ROOT#$package" --no-link --print-out-paths | tail -n 1
    fi
}

if "$SKIP_BUILD"; then
    echo "==> Reusing wm/sadewm and the latest sadeshell store output..."
else
    echo "==> Building sadewm..."
    make -B -C "$REPO_ROOT/wm" build
fi
if ! "$SKIP_BUILD"; then
    echo "==> Building sadeshell..."
fi
SHELL_OUTPUT="$(build_output sadeshell)"

WM_BIN="$REPO_ROOT/wm/sadewm"
SHELL_BIN="$SHELL_OUTPUT/bin/sadeshell"
[[ -x "$WM_BIN" ]] || { echo "ERROR: build did not produce $WM_BIN" >&2; exit 1; }
[[ -x "$SHELL_BIN" ]] || { echo "ERROR: build did not produce $SHELL_BIN" >&2; exit 1; }

echo "==> Starting Xephyr on $NESTED_DISPLAY ($SCREEN)..."
DISPLAY="$HOST_DISPLAY" Xephyr "$NESTED_DISPLAY" \
    -screen "$SCREEN" \
    -ac -fakexa \
    >"$SESSION_DIR/xephyr.log" 2>&1 &
XEPHYR_PID=$!
CHILD_PIDS+=("$XEPHYR_PID")

for _ in {1..50}; do
    if DISPLAY="$NESTED_DISPLAY" xdpyinfo >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$XEPHYR_PID" 2>/dev/null; then
        echo "ERROR: Xephyr exited during startup; see $SESSION_DIR/xephyr.log" >&2
        exit 1
    fi
    sleep 0.1
done
if ! DISPLAY="$NESTED_DISPLAY" xdpyinfo >/dev/null 2>&1; then
    echo "ERROR: Xephyr did not become ready; see $SESSION_DIR/xephyr.log" >&2
    exit 1
fi

X_EXTENSIONS="$(DISPLAY="$NESTED_DISPLAY" xdpyinfo -queryExtensions)"
for extension in Composite RENDER; do
    if ! grep -q "$extension" <<<"$X_EXTENSIONS"; then
        echo "ERROR: Xephyr does not expose the $extension extension." >&2
        exit 1
    fi
done

export DISPLAY="$NESTED_DISPLAY"
export XDG_RUNTIME_DIR="$RUNTIME_DIR"
SHELL_BIN_DIR="$(dirname "$SHELL_BIN")"
export PATH="$SHELL_BIN_DIR:$PATH"

# Xephyr has no GLX extension. Qt Quick's software scene graph still creates
# ARGB windows which Picom can composite over the Xephyr root window.
export QT_QPA_PLATFORM=xcb
export QT_QUICK_BACKEND=software
export QT_XCB_NO_XI2=1
export PYTHONFAULTHANDLER=1

echo "==> Starting sadeshell..."
"$SHELL_BIN" >"$SESSION_DIR/sadeshell.log" 2>&1 &
SHELL_PID=$!
CHILD_PIDS+=("$SHELL_PID")

DISPLAY_NAME="${NESTED_DISPLAY#:}"
DISPLAY_NAME="${DISPLAY_NAME%%.*}"
SHELL_SOCKET="$RUNTIME_DIR/sadeshell-$DISPLAY_NAME.sock"
for _ in {1..300}; do
    [[ -S "$SHELL_SOCKET" ]] && break
    if ! kill -0 "$SHELL_PID" 2>/dev/null; then
        echo "ERROR: sadeshell exited during startup; see $SESSION_DIR/sadeshell.log" >&2
        exit 1
    fi
    sleep 0.1
done
if [[ ! -S "$SHELL_SOCKET" ]]; then
    echo "ERROR: sadeshell IPC was not ready; see $SESSION_DIR/sadeshell.log" >&2
    exit 1
fi

echo "==> Starting Picom (XRender)..."
picom --config /dev/null --backend xrender \
    >"$SESSION_DIR/picom.log" 2>&1 &
PICOM_PID=$!
CHILD_PIDS+=("$PICOM_PID")
sleep 0.4
if ! kill -0 "$PICOM_PID" 2>/dev/null; then
    echo "ERROR: Picom exited during startup; see $SESSION_DIR/picom.log" >&2
    exit 1
fi

echo "==> Starting sadewm..."
"$WM_BIN" -d >"$SESSION_DIR/sadewm.log" 2>&1 &
WM_PID=$!
CHILD_PIDS+=("$WM_PID")
sleep 0.4
if ! kill -0 "$WM_PID" 2>/dev/null; then
    echo "ERROR: sadewm exited during startup; see $SESSION_DIR/sadewm.log" >&2
    exit 1
fi

if "$START_TEST_WINDOWS" && command -v xterm >/dev/null 2>&1; then
    echo "==> Opening test windows..."
    xterm -title "SADE terminal one" -geometry 72x20+80+100 \
        >"$SESSION_DIR/xterm-one.log" 2>&1 &
    CHILD_PIDS+=("$!")
    xterm -title "SADE terminal two" -geometry 72x20+520+260 \
        >"$SESSION_DIR/xterm-two.log" 2>&1 &
    CHILD_PIDS+=("$!")
    sleep 0.8
fi

if "$OPEN_OVERLAY"; then
    echo "==> Opening the transparent window-picker overlay..."
    if ! "$SHELL_BIN" --open-window-picker; then
        echo "ERROR: sadeshell did not open the overlay; see $SESSION_DIR/sadeshell.log" >&2
        exit 1
    fi
fi

echo
echo "Nested session is running on $NESTED_DISPLAY."
echo "Use Alt+S to toggle the picker; press Ctrl+C here to stop everything."
echo "Logs: $SESSION_DIR"

while :; do
    for process_spec in \
        "Xephyr:$XEPHYR_PID:xephyr.log" \
        "sadewm:$WM_PID:sadewm.log" \
        "Picom:$PICOM_PID:picom.log" \
        "sadeshell:$SHELL_PID:sadeshell.log"; do
        IFS=: read -r process_name process_pid process_log <<<"$process_spec"
        if ! kill -0 "$process_pid" 2>/dev/null; then
            echo "ERROR: $process_name stopped; see $SESSION_DIR/$process_log" >&2
            exit 1
        fi
    done
    sleep 0.5
done
