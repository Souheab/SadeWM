# Validation record

Local validation on 2026-09-26, x86_64 Linux, using the pinned Nix development
shell: Rust/Cargo/Clippy 1.94.0, Go 1.26.1 and Python 3.13.12. The Go reference is
commit `941662afe41dc785d0f04e3bc6983f8ec7bb3b76`; `xdrive` was initialized at its
recorded revision `2bd6d82b30ad6d2fadfa059524bd1e4495c106ae` before baselines.

## Automated checks

| Check | Result |
|---|---|
| Cargo unit tests | 30 passed |
| Cargo formatting and Clippy, all targets, warnings denied | Passed |
| Existing Go unit tests | All five packages passed |
| Existing Python shell/settings unit tests | 110 passed |
| Existing X11 + desktop integration tests against Go | 100 passed |
| Existing X11 + desktop integration tests against Rust | 100 passed |
| Additional parity/regression cases | 14 passed, including two compositor variants |
| Rust runner selection and legacy binary override | Passed |
| Python Ruff on added/modified test files; shell syntax; whitespace checks | Passed |
| Nix Rust package, x86_64-linux | Passed, including all 30 Cargo tests and installed asset licenses |
| Nix package/app and NixOS Go/Rust session evaluation | Passed for x86_64-linux and aarch64-linux |

The final combined Rust run passed all 114 cases (100 existing plus 14 new).
The final Go re-run passed all 100 existing cases. The Sync acknowledgement
scenario was also re-run with a nonzero high word in its counter.

Private Xvfb servers, private D-Bus sessions, temporary HOME/XDG directories and
isolated sockets were used. Xephyr/picom additionally covers focus/hover,
Unicode and narrow titles, resize, opacity, minimize/restore, fullscreen/restore,
and destruction. Repeated decoration cycles return the WM's XRes counts to the
baseline. A 16-bit server verifies pixel conversion; optional RandR, Xinerama,
DPMS and ScreenSaver extensions were disabled in another scenario.

The differential cases preserve ordering while normalizing generated IDs and
atom numbers. They compare client/frame geometry, focus, stacking, tags, desktop
properties, layouts, configuration, keybindings, IPC omissions and errors,
including repeated JSON fields and focusing by frame ID. Confirmed Go bugs are
asserted explicitly, as described in [the parity checklist](parity.md).

Additional regressions cover fresh-server ownership refusal, SIGHUP exit and
subsequent scanning/reparenting of surviving clients, toolkit child focus amid
stale events, genuine focus stealing, keyboard/pointer moveresize cancellation,
real 64-bit Sync-counter throttling, acknowledgement and timeout fallback,
wallpaper root pixmaps and cleanup, and shutdown during a deliberately stalled mock xrandr command while
preserving a launched test application. Socket tests cover malformed/oversized
requests, latest-state subscriber queues and disconnected subscriber cleanup.

The Nix build used a clean source snapshot excluding ignored build outputs.
The standalone Cargo version reports the Git revision; a path-only Nix source
has no Git metadata and correctly reports `unknown`. Git flake builds use the
flake revision (including its dirty marker).

The Python runs emit existing dbus-next deprecation and host fontconfig parser
warnings. These are not failed checks. The Rust executable's dynamic dependencies
are libc, libm and libgcc_s; it links neither Cairo nor libX11.

## Release measurements

[benchmark.json](benchmark.json) contains the measured data and resource counts.
The reproducible runner is `tests/benchmark.py`; it measures one and twenty
windows in both tiled and floating layouts, with debug logging disabled. Each
case samples three seconds of idle CPU, 100 IPC requests and 100 focus requests.
This is a single local Xvfb run, not a statistical or hardware performance claim.

The runner asserts no membership/current-desktop writes during focus-only
operations, exactly 100 active-window writes, at most 202 client-state writes,
and identical XRes counts before window creation and after cleanup. Memory
retained for fonts/text caches is measured rather than treated as an X11 leak.

| Layout / windows | Go RSS (MiB) | Rust RSS (MiB) | Go IPC p95 (ms) | Rust IPC p95 (ms) | Go focus p95 (ms) | Rust focus p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| tiled / 1 | 11.36 | 8.49 | 0.110 | 0.085 | 1.173 | 0.771 |
| tiled / 20 | 14.25 | 8.61 | 0.326 | 0.424 | 2.275 | 1.188 |
| floating / 1 | 22.10 | 10.03 | 0.232 | 0.118 | 1.332 | 0.749 |
| floating / 20 | 24.87 | 10.17 | 0.447 | 0.427 | 5.244 | 2.698 |

RSS was lower for Rust in these scenarios. Latency varies by layout and request;
these samples do not establish a universal speedup. Both backends returned to
their baseline X11 resource counts after cleanup and met the same property-write
bounds. The raw data also includes empty/after-cleanup RSS, median latency,
thread/file-descriptor counts and idle CPU. Rust recorded no CPU ticks during
the three-second idle samples; Go recorded 0.333% in the 20-floating-window case
and no ticks in the other cases. This short sampling interval cannot establish
zero ongoing CPU use.

## Coverage limits

Native aarch64 compilation/execution was unavailable; derivations, apps and both
NixOS session selections were evaluated. Real GPU rendering, physical RandR
hotplug/mixed-scale monitors, DPMS wake, suspend/resume, big-endian X servers,
servers without Shape/Sync, and prolonged daily desktop use remain unverified.
This Xvfb supports disabling the other optional extensions, but not Shape/Sync.
No test changed the live desktop or the Go default, or suspended the host.
