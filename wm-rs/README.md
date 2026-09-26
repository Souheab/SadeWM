# sadewm-rs

An independent Rust 2024 implementation of the SADE X11 window manager. The Go
WM remains the default. Both use the X11 name `sadewm`, the same configuration,
IPC socket and companion applications. Never run both on the same display.

## Build and run

The pinned development shell provides Rust, Go, Python and the X11 test tools:

```sh
nix develop
cargo build --manifest-path wm-rs/Cargo.toml --release --locked
wm-rs/target/release/sadewm-rs -v
```

Rust 1.94 is the tested toolchain. `Cargo.lock` pins dependencies. The executable
accepts `-v`, `-d`, `-t`, `-c`, `-custom-config`, `-no-config`, their double-dash
spellings and Go-style `-flag=value`. `-v` reports Rust and the build revision;
set `SADEWM_REVISION` when building without Git metadata.

Run `sadewm-rs` from an X11 session or a private nested X server. Configuration
comes from `~/.config/sade/{wm.toml,settings.toml,startup.sh}`. `-custom-config`
changes all three paths; `-c` overrides only `wm.toml`. `-no-config` skips those
files. The wallpaper remains `~/.config/sade/wp.jpg`, including under
`-no-config`, matching Go. `SADEWM_SOCKET` overrides the usual display-derived
`/tmp/sadewm-*.sock` name. `SIGHUP`, `SIGINT` and `SIGTERM` shut down; `SIGUSR1`
logs Rust state diagnostics. Logs and the FIFO remain under
`$XDG_DATA_HOME/sadewm` (or `~/.local/share/sadewm`).

## Opt-in Nix package and session

```sh
nix build .#sadewm-rs
nix run .#sadewm-rs -- -v
```

For a NixOS system importing this flake's module:

```nix
services.xserver.windowManager.sadewm = {
  enable = true;
  backend = "rust"; # "go" remains the default
};
```

The SADE session, shell, settings application, greeter and user services stay
available. No live session switch is performed by building or testing this
package. Before new files are tracked by Git, use `path:.#sadewm-rs` with Nix
because Git flakes omit untracked files.

## Validation

Initialize the reference submodule at its recorded revision:

```sh
git submodule update --init --recursive xdrive
cargo fmt --manifest-path wm-rs/Cargo.toml --check
cargo clippy --manifest-path wm-rs/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path wm-rs/Cargo.toml --locked
./x11-testing/run_tests.sh                     # Go default
./x11-testing/run_tests.sh --backend rust
```

`SADEWM_BIN` and `SADEWM_TEST_BINARY` can both select an existing X11 test binary;
`SADEWM_BIN` takes precedence in the X11 runner. The desktop integration runner
also accepts either variable, preferring `SADEWM_TEST_BINARY` for compatibility.

```sh
SADEWM_TEST_BINARY="$PWD/wm-rs/target/release/sadewm-rs" \
  dbus-run-session --config-file=tests/integration/session.conf -- \
  python -m pytest tests/integration -q

SADEWM_GO_BINARY="$PWD/wm/sadewm" \
SADEWM_RUST_BINARY="$PWD/wm-rs/target/release/sadewm-rs" \
  dbus-run-session --config-file=tests/integration/session.conf -- \
  python -m pytest wm-rs/tests -q
```

The differential suite normalizes generated window IDs, compares atom names
rather than numeric IDs, excludes generated timestamps, and preserves client,
focus and stacking order. It also runs Xephyr/picom visual lifecycle checks,
16-bit rendering and optional-extension checks. All servers, homes and sockets
are private. `SADEWM_TEST_XEPHYR=1` runs the desktop integration suite under
Xephyr/picom too.

For an informational release comparison:

```sh
python wm-rs/tests/benchmark.py --go "$PWD/wm/sadewm" \
  --rust "$PWD/wm-rs/target/release/sadewm-rs" --output /tmp/wm-benchmark.json
```

See [the parity checklist](docs/parity.md) for coverage, intentional differences
and outstanding hardware validation, and [validation results](docs/validation.md)
for recorded runs.

## Implementation

`main.rs` only parses CLI options and starts the session. Configuration, typed
actions/state, geometry, rendering, X11 property validation, IPC and subprocess
services are independently testable. `wm/` owns the connection and all live
client/monitor state on one thread. It drains x11rb-buffered events before
polling X11, IPC and signal sockets, with bounded event batches and timers.

Rendering uses tiny-skia and cosmic-text CPU buffers, native X11 pixel formats
and chunked uploads. There is no Cairo or libX11 renderer. Fonts use the system
sans-serif family, with the bundled DejaVu Sans fallback. Font and keysym-table
licenses are in `assets/`. Clients, frames, titlebars, border windows, cursors,
pixmaps and GCs have explicit cleanup paths. Launched applications survive WM
exit; worker-managed display commands have deadlines, isolated process groups,
and cancellation on WM shutdown.
