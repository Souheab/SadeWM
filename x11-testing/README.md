# X11 Testing Suite for sadewm

Headless X11 testing tools for debugging and validating the sadewm window manager.

## Components

- **`helpers.py`** — Python library: X11 event simulation, IPC client, WM state queries
- **`mouse/test_drag.py`** — xdrive-based tests for Mod+Button1 drag (button press, tiled swap, floating move)
- **`run_tests.sh`** — Shell wrapper: starts Xvfb, launches sadewm, runs tests, collects logs

## Quick Start

```bash
# Run all tests (starts Xvfb + sadewm automatically)
./x11-testing/run_tests.sh

# Run with debug logging from sadewm
./x11-testing/run_tests.sh -d

# Run a single test file against an already-running sadewm
DISPLAY=:98 python3 -m pytest x11-testing/mouse/test_drag.py -v
```

## Requirements

- Go toolchain (to build sadewm)
- `Xvfb` (managed automatically by xdrive's `VirtualDisplay`; must be installed)
