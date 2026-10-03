# sadewm

The Rust 2024 SADE X11 window manager and sole WM implementation.

## Build and run

```sh
nix develop
cargo build --manifest-path wm/Cargo.toml --release --locked
wm/target/release/sadewm -v
```

`Cargo.lock` pins dependencies. The executable accepts `-v`, `-d`, `-t`, `-c`,
`-custom-config`, `-no-config`, their double-dash spellings, and `-flag=value`.
Version output reports Rust and the build revision; set `SADEWM_REVISION` when
building without Git metadata.

Run `sadewm` from an X11 session or a private nested X server. Configuration
comes from `~/.config/sade/{wm.toml,settings.toml,startup.sh}`. `-custom-config`
changes all three paths; `-c` overrides only `wm.toml`. `-no-config` skips those
files. The wallpaper remains `~/.config/sade/wp.jpg`, including under
`-no-config`. `SADEWM_SOCKET` overrides the usual display-derived
`/tmp/sadewm-*.sock` name. SIGHUP, SIGINT and SIGTERM shut down; SIGUSR1 logs
state diagnostics. Logs and the FIFO remain under `$XDG_DATA_HOME/sadewm`
(or `~/.local/share/sadewm`).

## Interactive nested desktop

```sh
nix develop
./wm/scripts/run_xephyr_session.sh
```

This builds the release WM and packaged SadeShell, then starts Xephyr on `:7`
with picom's XRender backend, SadeShell and two test terminals. Alt+S toggles
the window picker, which opens automatically. Qt uses software rendering.
The session has a private D-Bus bus, WM socket, logs and control FIFO, and skips
WM configuration and `startup.sh`.

Use `--display :8` if `:7` is occupied, `--screen 1600x900x24` to change the
window size, or `--no-overlay --no-test-windows` for a clean desktop.
`--skip-build` reuses the existing release WM and Nix SadeShell output.
Ctrl+C stops the session's processes; logs remain in the printed `/tmp` directory.

## Nix package and session

```sh
nix build .#sadewm
nix run .#default -- -v
```

The default package and `sadewm` package contain the desktop bundle. For a
standalone WM, `nix build .#sadewm-rs` remains supported; its output contains
`sadewm` and the compatibility symlink `sadewm-rs`. `nix run .#sadewm-rs -- -v`
also remains supported. Both names execute the same Rust WM.

For a NixOS system importing this flake's module:

```nix
services.xserver.windowManager.sadewm.enable = true;
```

Remove the former `backend` option. An explicit `"rust"` value is accepted with
a deprecation warning; `"go"` is rejected with migration guidance. The SADE
session includes the shell, settings application, greeter and user services.
Building or testing does not switch the running desktop.

## Validation

```sh
nix develop
git submodule update --init --recursive xdrive
cargo fmt --manifest-path wm/Cargo.toml --check
cargo clippy --manifest-path wm/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path wm/Cargo.toml --locked
cargo build --manifest-path wm/Cargo.toml --release --locked
./x11-testing/run_tests.sh
SADEWM_TEST_BINARY="$PWD/wm/target/release/sadewm" \
  dbus-run-session --config-file=tests/integration/session.conf -- \
  python -m pytest wm/tests tests/integration -q
nix flake check -L
```

`SADEWM_BIN` and `SADEWM_TEST_BINARY` select an existing binary. The X11 runner
prefers `SADEWM_BIN`; the WM and desktop integration suites prefer
`SADEWM_TEST_BINARY`. Tests use private displays, homes and sockets. Setting
`SADEWM_TEST_XEPHYR=1` also exercises desktop integration under Xephyr/picom.

For informational release measurements:

```sh
python wm/tests/benchmark.py --binary "$PWD/wm/target/release/sadewm" \
  --output /tmp/wm-benchmark.json
```

See [coverage](docs/coverage.md) and [validation](docs/validation.md). Historical
Go/Rust measurements are preserved as dated records, rather than current tests.

## Implementation

`main.rs` parses CLI options and starts the session. Configuration, typed
state/actions, geometry, rendering, X11 property validation, IPC and subprocess
services are independently testable. `src/wm/` owns the connection and live
client/monitor state on one thread, with bounded event batches and timers.

Rendering uses tiny-skia and cosmic-text CPU buffers, native X11 pixel formats
and chunked uploads. Fonts use the system sans-serif family with a bundled
DejaVu Sans fallback. Font and keysym-table licenses are in `assets/`.
Clients, decorations and server resources have explicit cleanup paths.
Launched applications survive WM exit; worker-managed display commands have
deadlines, isolated process groups and cancellation on shutdown.
