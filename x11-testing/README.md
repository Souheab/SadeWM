# X11 Testing Suite for sadewm

Headless X11 testing tools for debugging and validating the sadewm window manager.

## Components

- **`helpers.py`** — Python library: X11 event simulation, IPC client, WM state queries
- **`test_mouse_drag.py`** — Automated test for Mod+Button1 drag (tiled swap + floating move)
- **`run_tests.sh`** — Shell wrapper: starts Xvfb, launches sadewm, runs tests, collects logs

## Quick Start

```bash
# Run all tests (starts Xvfb + sadewm automatically)
./x11-testing/run_tests.sh

# Run with debug logging from sadewm
./x11-testing/run_tests.sh -d

# Run a single test script against an already-running sadewm
DISPLAY=:97 python3 x11-testing/test_mouse_drag.py
```

## Requirements

- `xvfb`, `xdotool`, `socat`, `python3-xlib`, `x11-apps` (xeyes)
- Go toolchain (to build sadewm)
