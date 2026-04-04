#!/usr/bin/env bash
# debug_xvfb.sh — run sadeshell in Xvfb, capture gdb backtrace and screenshot
# Usage: ./debug_xvfb.sh [--screenshot]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
ARTIFACT_DIR="$REPO_ROOT/debug_artifacts"
DISPLAY_NUM=97
DISPLAY_ENV=":$DISPLAY_NUM"
SCREENSHOT="$ARTIFACT_DIR/sadeshell_xvfb.png"
BACKTRACE_FILE="$ARTIFACT_DIR/backtrace.txt"
LOG_FILE="$ARTIFACT_DIR/sadeshell_run.log"

mkdir -p "$ARTIFACT_DIR"

# ── helpers ──────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }

need() { command -v "$1" &>/dev/null || die "missing: $1 (hint: $2)"; }

take_screenshot() {
    local out="$1"
    # Try scrot, then import (ImageMagick), then xwd+convert
    if command -v scrot &>/dev/null; then
        DISPLAY="$DISPLAY_ENV" scrot "$out" 2>/dev/null && return 0
    fi
    if command -v import &>/dev/null; then
        DISPLAY="$DISPLAY_ENV" import -window root "$out" 2>/dev/null && return 0
    fi
    if command -v xwd &>/dev/null && command -v convert &>/dev/null; then
        DISPLAY="$DISPLAY_ENV" xwd -root -silent | convert xwd:- "$out" && return 0
    fi
    echo "WARN: no screenshot tool found (tried scrot, import, xwd+convert)" >&2
    return 1
}

# ── kill any leftover Xvfb on our display ─────────────────────────────────
pkill -f "Xvfb $DISPLAY_ENV" 2>/dev/null || true
sleep 0.3

# ── start Xvfb ────────────────────────────────────────────────────────────
echo "Starting Xvfb $DISPLAY_ENV ..."
Xvfb "$DISPLAY_ENV" -screen 0 1920x1080x24 -ac &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null; true' EXIT
sleep 1

# ── build if needed ───────────────────────────────────────────────────────
if [[ ! -x "$REPO_ROOT/result/bin/sadeshell" ]]; then
    echo "Building sadeshell flake..."
    nix build "$REPO_ROOT" --no-link 2>&1 | tee "$ARTIFACT_DIR/nix_build.log" || \
        die "nix build failed — see $ARTIFACT_DIR/nix_build.log"
    # symlink result
    nix build "$REPO_ROOT" 2>&1 | tail -3
fi

PYSHELL="$REPO_ROOT/result/bin/sadeshell"
PYTHON_BIN="$(grep '^exec ' "$PYSHELL" | awk '{print $2}' | tr -d '"')"
[[ -z "$PYTHON_BIN" ]] && PYTHON_BIN="$(head -5 "$PYSHELL" | grep python | awk '{print $NF}')"

# ── capture environment from wrapper ─────────────────────────────────────
# Source the wrapper env without exec-ing the python binary
ENV_SCRIPT="$(mktemp --suffix=.sh)"
# Extract env setup lines before the final exec, write to temp script
grep -v '^#!' "$PYSHELL" | grep -v '^exec ' > "$ENV_SCRIPT"
echo "export DISPLAY=$DISPLAY_ENV" >> "$ENV_SCRIPT"
chmod +x "$ENV_SCRIPT"

# ── run with gdb backtrace ────────────────────────────────────────────────
echo "Running sadeshell under gdb in Xvfb $DISPLAY_ENV ..."
echo "Backtrace will be written to: $BACKTRACE_FILE"

(
    # shellcheck source=/dev/null
    source "$ENV_SCRIPT"
    DISPLAY="$DISPLAY_ENV"
    export DISPLAY

    # Force software rendering to avoid SIGABRT from GLX in virtual displays.
    # QT_XCB_GL_INTEGRATION=none prevents libqxcb from loading the GLX plugin
    # (which calls qFatal when Xvfb has no GLX vendor).  The other flags ensure
    # Qt Quick uses a software path that requires no GPU.
    export QT_XCB_GL_INTEGRATION=none
    export QT_OPENGL=software
    export LIBGL_ALWAYS_SOFTWARE=1
    export QSG_RHI_BACKEND=software
    export QSG_RENDER_LOOP=basic
    export QT_XCB_NO_XI2=1

    if command -v gdb &>/dev/null; then
        gdb -batch \
            -ex "set pagination off" \
            -ex "set print thread-events off" \
            -ex "handle SIGSEGV stop print" \
            -ex "handle SIGABRT stop print" \
            -ex "run" \
            -ex "thread apply all bt full" \
            -ex "info registers" \
            -ex "quit" \
            --args "$PYTHON_BIN" -m sadeshell.main \
            > "$BACKTRACE_FILE" 2>&1 &
        GDB_PID=$!
    else
        echo "gdb not found — running without debugger" >&2
        "$PYTHON_BIN" -m sadeshell.main > "$LOG_FILE" 2>&1 &
        GDB_PID=$!
    fi

    # wait up to 8 s, take screenshot if we're still alive
    for i in $(seq 1 8); do
        sleep 1
        if ! kill -0 "$GDB_PID" 2>/dev/null; then
            echo "Process exited after ${i}s"
            break
        fi
        if [[ $i -eq 5 ]]; then
            echo "App appears running — taking screenshot..."
            take_screenshot "$SCREENSHOT" && echo "Screenshot saved: $SCREENSHOT" || true
        fi
    done

    # give gdb a bit more time to finish writing the trace
    wait "$GDB_PID" 2>/dev/null || true
) 2>&1 | tee "$LOG_FILE"

rm -f "$ENV_SCRIPT"

echo ""
echo "══════════════════════════════════════════"
if [[ -s "$BACKTRACE_FILE" ]]; then
    echo "GDB backtrace ($BACKTRACE_FILE):"
    echo "══════════════════════════════════════════"
    # Show the crash signal and Thread 1 frames, not all threads
    awk '/received signal|Thread 1 \(LWP/{found=1} found{print; if(/^$/ && found>1){exit} found++}' \
        "$BACKTRACE_FILE" | head -60 || cat "$BACKTRACE_FILE" | tail -80
fi
echo "══════════════════════════════════════════"
echo "Artifacts in: $ARTIFACT_DIR"
[[ -f "$SCREENSHOT" ]] && echo "Screenshot:   $SCREENSHOT"
