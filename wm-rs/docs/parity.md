# Go / Rust parity checklist

Reference: `wm/`, its unit tests, the [EWMH matrix](../../wm/docs/ewmh-1.5.md),
`x11-testing`, and `tests/integration`. The recorded `xdrive` revision is
`2bd6d82` (the submodule pointer is unchanged). This checklist concerns
implemented behavior; physical hardware coverage is listed separately below.

| Status | Subsystem | Implementation and checks |
|---|---|---|
| Implemented | CLI and configuration | Flags/path precedence, defaults, scalar reload, rules, key overrides/removals and tag keys; Rust unit tests and configuration differential scenario |
| Implemented | Typed state and layouts | Stable XIDs and monitor IDs, separate layout/focus/manage order, per-tag views/layout/direction/master/gaps; geometry tests and ordered differential snapshots |
| Implemented | Focus and input | ICCCM input models, fresh server timestamps, timestamp wraparound, modal focus, directional focus/swap, monitor transfers, key remapping, replayed clicks, snapping, final drag samples |
| Implemented | Lifecycle | Scan/map/withdraw/destroy, reparenting/save set, minimize/restore, independent maximize axes, fullscreen restore slot, sticky/shade/modal/urgency, docks/desktops/transients |
| Implemented | Decorations | 28px titlebar, rounded Shape masks, border companions, palette/buttons/hover, Unicode text, narrow windows, resize, frame opacity; pixel-format tests and Xvfb/Xephyr/picom resource cycles |
| Implemented | Root EWMH | WM_Sn selection/MANAGER announcement, WM identity, desktop/workarea/show-desktop, original management order and actual server stacking, conditional supported registry |
| Implemented | Client EWMH/ICCCM | Window types, allowed actions, state transitions, activation policy, timestamped focus/close/ping, struts, desktop mapping, gravity, interactive moveresize/cancel, sync counters and timeout fallback |
| Implemented | Monitors | Xinerama discovery and indices, physical intersection, RandR topology events, transfers, fullscreen spanning, partial struts; unit and two-screen Xvfb tests |
| Implemented | IPC | Every Go command/response shape, omitted fields, errors, newline replies, 64KiB limit, two-second transport/response deadlines, latest-state tag stream; socket tests and differential scenarios |
| Implemented | Session | Startup/reload, bounded xrandr execution, resident shell IPC and fallback, logging/FIFO, DPMS and idle suspend, JPEG cover wallpaper/root pixmap, signal diagnostics and shutdown |
| Implemented | Failure/cleanup | Missing optional extensions, stale/destroyed clients, ownership refusal, withdrawal, signal exit, explicit owned resource release; unit tests, private-server lifecycle tests and XRes assertions |
| Implemented | Packaging | Independent locked Cargo package; Nix package/app and tooling; NixOS backend enum with Go default and retained companion services |

The Rust registry is checked against the Go compliance matrix. As in Go, the
WM does not claim compositing-manager ownership, icon management, virtual roots,
scrolling desktops or pager-owned desktop layout. Picom remains separate.

## Intentional differences and confirmed Go bugs

* **Maximizing preserves tiling membership.** Rust expands tiled windows within
  the work area without adding a titlebar or setting the floating flag, including
  application requests and maximized state supplied before mapping. Their tile
  slots remain reserved and track layout changes for restoration. Floating windows
  retain their decorations and restore their previous geometry. Rust regressions
  cover keyboard/application/startup requests, independent axes, fullscreen and
  shade round trips.
* **Startup key/rule overrides take effect immediately.** Go's `main` applies
  scalar TOML values, then `wm.New()` installs default keys/rules; custom
  keys/rules are first installed on reload. The Rust configuration scenario
  reproduces that difference (a removed Super+Q binding stays present in Go
  until reload) and checks that the reloaded bindings match exactly.
* **Reload applies master count/size to the current tag immediately.** Go updates
  stored per-tag values but leaves the current monitor values unchanged until
  switching tags. The configuration scenario reproduces this with `nmaster=0`,
  checks immediate Rust application and compares both after switching tags.
* **A maximized floating frame stays within the work area.** Go places the client
  content at the work-area top, leaving its 28px titlebar above that boundary.
  Rust reserves those 28px inside the maximized frame. The maximized-frame reproducer checks both backends; the axes/restore test
  checks the frame boundary and exact restoration; horizontal-only maximization
  retains the original vertical geometry.
* **Invalid negative/oversized dimensions are bounded.** Go converts negative
  integer border/gap/offset values to unsigned values. Rust clamps these values
  to 0–65535, and bounds master count and master fraction. Unit regressions cover
  the negative gap/master-count reproducer and atomic malformed reloads.
* Rendering uses system sans-serif/cosmic-text/tiny-skia rather than Cairo.
  Glyph metrics and antialiasing may differ. Design geometry, colors, controls,
  Shape masks and frame opacity are preserved.
* Diagnostics and version output identify Rust. IPC has at most 128 connected
  peers and subprocess work has a 32-job queue, two workers and at most 256
  tracked application children per worker. Saturation cannot create unbounded
  worker threads. Shaped titles use a cache bounded by 64 entries and 64KiB of
  source text; glyph image caches are also bounded. These limits do not change successful command response shapes.

The Go implementation remains available and unchanged; the startup/reload bugs
above are explicitly reproduced rather than silently normalized away.

## Hardware and environment validation

Xvfb tests exercise deterministic geometry/protocol behavior. Xephyr with
picom's XRender backend exercises composited decoration capture, hover, opacity,
resize, Unicode/narrow titles and destruction. A 16-bit Xvfb session exercises
native pixel upload; unit tests cover big-endian RGB and scanline padding.

Still requiring physical or additional-platform validation:

- Real RandR cable hotplug, mixed monitor sizes/scales and GPU/compositor timing.
- Physical DPMS power-off/wake and system suspend/resume. Tests must not suspend
  the developer's computer.
- Native aarch64 execution/build (the Nix derivation/app are evaluated).
- A real big-endian X server, unusual visuals, and servers lacking Shape or Sync.
  This Xvfb can disable RandR, Xinerama, DPMS and ScreenSaver, but not Shape/Sync.
- Long-running desktop use with applications outside the existing test suite.

No claim of a universal speedup is made. The benchmark records release RSS,
idle CPU, IPC/focus latency, property writes and server resource counts for
repeatable local scenarios; it is not a GPU or hardware benchmark.
