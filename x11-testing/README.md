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

# Run one test file (the runner enables WM debug logging)
./x11-testing/run_tests.sh -t test_sadewm_ipc.py

# Run a single test file against an already-running sadewm
DISPLAY=:98 python3 -m pytest x11-testing/mouse/test_drag.py -v
```

## Requirements

- Rust/Cargo toolchain (provided by `nix develop`)
- `Xvfb` (managed automatically by xdrive's `VirtualDisplay`; must be installed)
