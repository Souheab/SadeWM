just my hobby project building a basic X11 desktop environment

## Window manager implementations

Active window-manager development is focused on the Rust backend in `wm-rs/`.
The Go backend in `wm/` is frozen for now and retained as a reference.

The Go WM in `wm/` remains the default. An independent Rust implementation in
[`wm-rs/`](wm-rs/README.md) builds as `sadewm-rs` and uses the same configuration,
X11 identity, IPC, shell and settings app. Build it with `nix build .#sadewm-rs`
or `cargo build --manifest-path wm-rs/Cargo.toml --release --locked`.

NixOS users can opt in with
`services.xserver.windowManager.sadewm.backend = "rust";` (default: `"go"`).
For an interactive nested Rust desktop with Xephyr, picom and SadeShell, run
`nix develop` followed by `./wm-rs/scripts/run_xephyr_session.sh`.
See the [parity checklist](wm-rs/docs/parity.md) and
[validation results](wm-rs/docs/validation.md) for tested behavior, documented
differences and remaining hardware checks.

## Nix packaging

The flake pins `nixos-unstable`. Update its inputs with `nix flake update`, then
run `nix flake check -L`. Checks build both WM packages and the desktop bundle,
evaluate the NixOS modules with both backends, and start the installed shell,
settings app and greeter on a private Xvfb display and D-Bus session. The startup
check also verifies that the WM uses the session's `systemctl` and that the shell
restores the session environment for launching applications.

Using `inputs.sadewm.inputs.nixpkgs.follows = "nixpkgs"` in a system flake is
supported; the system flake's lock then chooses the Qt/Python versions instead of
this repository's lock. Update the system flake's SadeWM input to pick up package
fixes. To validate another pinned nixpkgs, use
`nix flake check --override-input nixpkgs github:NixOS/nixpkgs/<revision> --no-write-lock-file`.

WM wrappers provide `xrandr` only as a fallback and use the host's systemd tools.
The shell service uses normal NixOS `path` composition with user and system
profiles first. SadeShell's Qt, Python and library paths stay private to the shell
when it launches desktop applications. Its custom QML uses Qt's Basic controls
style, so the bar does not depend on the host's KDE/Kirigami QML installation.

## Config

sadewm looks for user configuration in `~/.config/sade` by default:

- `wm.toml` overrides window manager settings such as appearance, colors, layout, rules, and keybindings.
- `settings.toml` stores display and X11 session power settings. The `[power]`
  `monitor_timeout_minutes` value controls when DPMS turns monitors off, while
  `sleep_timeout_minutes` controls when the system is suspended; `0` disables
  either timeout.
- `startup.sh` runs once when sadewm starts.

Use `sadewm -c /path/to/wm.toml` to load a specific window manager config, `sadewm -custom-config /path/to/dir` to use another config directory, or `sadewm -no-config` to skip user config and startup scripts. The default keybinding `Super+Shift+r` reloads the active config.

## Roadmap

### Improvements
- Improve the UI appearance

### Bugs/Issues to Fix
- Settings app scrolling on numerical selector causes numerical change
- Weird floating window and titlebar behavior
- Systray not working correctly for some apps (Qt apps)
- Picom needs to be run with --no-frame-pacing
