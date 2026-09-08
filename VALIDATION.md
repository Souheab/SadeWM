# Reliability and performance validation

Validated on 2026-09-07, Linux x86_64, using the pinned Nix development
environment (Python 3.13.12, real PySide6 objects). This report covers the
reliability implementation plus the final notification-lifecycle and EWMH
membership fixes. It is not a claim of physical-device certification.

## Results

- Combined shell, settings, and xdrive Python suites: 163 passed.
- Go: all five packages passed, including bounded display-command execution.
- Ruff: passed; `git diff --check`: passed.
- Private Xvfb/D-Bus integration: 15 passed.
- Private Xephyr nested inside Xvfb, with picom's XRender backend: 6 passed.
- Final installed Nix shell: singleton and all six first-use overlays passed.
- All three Nix outputs built: `sadeshell`, `sadesettings`, and `sadewm`.
- Wheel and source distribution both installed into temporary directories
  outside the checkout. Package identity, lightweight imports, console-script
  presence, and all QML/qmldir/SVG resources were verified.

The final pass found and fixed two additional defects: an expiring
notification's Python timer closure could crash during later Qt event
processing, and a legacy append duplicated the newest window in
`_NET_CLIENT_LIST`. Expiry now uses a QObject-bound slot; deferred popup work
uses an owned, cancellable timer. Client membership has one publication path.
Regression tests cover both defects.

The runs produced dependency deprecation warnings and host Fontconfig
configuration warnings. These did not prevent QML loading or test completion.

## Performance samples

The pre-change baseline is commit `2b28ec1`, extracted into temporary
directories. Its WM only received a logging-path adjustment to keep logs
isolated. Baseline shell imports used a temporary source-layout symlink;
neither the working checkout nor the live desktop was replaced.

Numbers below are single-run samples, not statistically significant speed
guarantees. Tests ran on private 1280x800 X servers with software Qt rendering.
The shell comparison used the same final WM for both shell versions, isolating
shell changes. Timing gates intentionally do not depend on hardware speed.

### Focus: ten IPC requests per sample

| Windows | Median IPC ms, before → after | Client state writes, before → after | Membership writes, before → after |
| --- | --- | --- | --- |
| 1 | 0.286 → 0.160 | 10 → 0 | 20 → 0 |
| 10 | 0.894 → 0.181 | 100 → 18 | 20 → 0 |
| 50 | 3.974 → 0.874 | 500 → 18 | 20 → 0 |

Writes are observed X PropertyNotify events, not a count of every wire-level
X request. Tests gate on zero membership rewrites and at most two client-state
writes per focus request. Separate checks verify manage order, class refresh,
modifier mapping notifications, deleted-property recovery, and stacking against
the server's actual window tree.

### Shell readiness and idle work

| Windows | Startup ms, before → after | Picker mapping ms, before → after | Idle CPU %, before → after | Idle CLI launches, before → after |
| --- | --- | --- | --- | --- |
| 1 | 2151 → 2108 | 330 → 63 | 1.25 → 0.67 | 12 → 0 |
| 10 | 2125 → 2328 | 336 → 87 | 1.17 → 0.75 | 12 → 0 |
| 50 | 2160 → 2268 | 331 → 61 | 1.75 → 1.25 | 12 → 0 |

Startup means a mapped shell window and its singleton socket are present.
Picker latency measures command-to-native-window mapping, not completion of
thumbnail loading or animation. There is no demonstrated startup improvement.
Readiness polling has approximately 20 ms resolution.

CPU is process CPU time divided by a 12-second closed-picker interval, expressed
as a percentage of one CPU. The interval covers the former eight-/ten-second
Bluetooth/Wi-Fi poll timers. A Python audit hook records even short-lived Python
subprocess launches; it does not trace native-library child creation. Each
baseline idle sample launched ten `bluetoothctl` and two `nmcli` processes;
the final samples launched none. Radio services were not exercised against
physical adapters, so these numbers describe idle monitoring, not scanning or
authentication throughput.

### Resource bounds

| Windows | Final cached files | Final cached bytes | Final open descriptors, start → end of idle |
| --- | --- | --- | --- |
| 1 | 1 | 1085 | 33 → 33 |
| 10 | 10 | 6011 | 34 → 34 |
| 50 | 16 | 3219 | 33 → 33 |

These are highly compressible synthetic-window previews, not representative
photographic PNG sizes. The 50-window case requests the viewport plus one
prefetched row, not all 50 thumbnails. Independent unit tests exercise both
the 128-file and 32 MiB eviction limits, the two-worker bound, deduplicated
pending requests, and cancellation when the picker closes.

Thirty captures of a 4096x2160 window left the capture connection's X resource
counts unchanged. Forcing the non-Render fallback on that window correctly
returned no image because the raw capture exceeds 32 MiB. Smaller fallback
captures and RGB565/big-endian decoding also passed. Xephyr/picom exercised the
composited capture path without acquiring compositor ownership.

## Reproduction

From the repository root, enter `nix develop` and run:

```sh
python -m pytest -q
ruff check shell/src/sadeshell shell/tests settings-app tests/integration
(cd wm && go test ./... && go build -o /tmp/sadewm-validation ./cmd/sadewm)
dbus-run-session --config-file=tests/integration/session.conf -- \
  python -m pytest tests/integration -v -s
SADEWM_TEST_XEPHYR=1 dbus-run-session \
  --config-file=tests/integration/session.conf -- \
  python -m pytest tests/integration/test_desktop.py \
  -k 'minimize_restore or shell_lazy or property_republication or large_capture' -v
nix build .#sadeshell .#sadesettings .#sadewm --no-link
```

Set `SADESHELL_TEST_BINARY` to an installed shell executable to repeat the
`shell_lazy` smoke test against that package. The integration suite prints
JSON measurement rows with `-s`. `SADESHELL_BENCH_SOURCE` can point at an
isolated pre-change import directory for shell measurements;
`SADEWM_TEST_BINARY` and `SADEWM_BENCH_BASELINE=1` select a baseline WM for
focus measurements. Do not set these baseline overrides for acceptance runs.

All desktop integration tests create private X servers, private session buses,
temporary configuration/data/cache/runtime directories, and terminate only
processes they own. They do not switch the user's WM or display settings.

## Coverage limits and manual follow-up

The following were not certified by this environment and remain manual release
checks, not silently treated as passes:

- Real NetworkManager authentication, Wi-Fi hardware scans, BlueZ pairing and
  device connections, and live MPRIS players with unusual implementations.
- Physical multi-monitor hotplug, negative-origin displays with differing
  scaling, GPU-driver-specific visuals, and exhaustive modal/dock interactions.
  Synthetic geometry/protocol tests do not replace these checks.
- Long-duration sessions with many changing 4K photographic windows. Current
  tests establish bounded queues/files and repeated-capture resource stability,
  not a multi-hour GPU/texture-memory soak.
- Total X protocol traffic and native-library subprocess counts. Property-write
  budgets and Python subprocess audit counts are measured explicitly instead.
- Non-Nix distro installation with independently resolved system libraries,
  Python 3.11/3.12, and aarch64. Wheel/sdist installation was verified outside
  the repository using the Nix-provided Python and system dependencies.

No deployment, live-desktop replacement, or commit is performed by validation.
