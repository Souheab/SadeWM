# sadeshell

Python 3.11+ and an EWMH-compatible X11 desktop are required.

From the repository root:

```sh
nix develop
python -m sadeshell.main
python -m pytest
```

Run the packaged Nix shell with `nix run .#sadeshell`.
The settings application has its own Python runtime: `nix run .#sadesettings`.

For an ordinary Python installation:

```sh
python -m venv .venv
. .venv/bin/activate
pip install ./shell
sadeshell
```

The distribution includes QML components, qmldir files and assets.
Qt's configured QML paths take precedence; split Nix installations have a
fallback cache under `$XDG_CACHE_HOME/sadeshell` (default `~/.cache/sadeshell`).
No generated package symlink or writable installation directory is required.

System dependencies include X11, libxcb (including Render and Composite),
the libraries required by Qt's xcb platform plugin, and PulseAudio or
PipeWire's PulseAudio compatibility server. Building xcffib from source may
also require libxcb development headers; see the
[xcffib installation instructions](https://github.com/tych0/xcffib).
NetworkManager and BlueZ are optional: unavailable services report errors in
their panels. `nmcli` is used only for an explicit Wi-Fi connection request.

Thumbnails are scaled by XRender without redirecting windows or claiming
compositor ownership. A missing Render extension allows one full-image fallback
at a time, capped at 32 MiB; the private image cache is capped at 128 files and
32 MiB. Only the picker viewport and one prefetched row request captures.

Notifications retain up to 200 history entries in memory for this process.
Timeout zero is persistent, -1 uses five seconds, and hover pauses expiry.
Closing/dismissing removes history; ordinary expiry retains it.

Build distributions with `python -m build shell`. The installed CLI also
supports `python -m sadeshell.main`, and IPC-only flags do not initialize Qt.

## Isolated integration checks

```sh
cd wm && go build -o /tmp/sadewm-validation ./cmd/sadewm && cd ..
dbus-run-session --config-file=tests/integration/session.conf -- \
  python -m pytest tests/integration -v
```

The checks start private X servers and a private session bus, use temporary XDG
directories, and terminate only processes they started. They do not require a
running user desktop.

See [the validation report](../VALIDATION.md) for final results, baseline/final
performance samples, Xephyr/picom commands, and explicit hardware coverage gaps.
