# EWMH 1.5 compliance matrix

This document describes sadewm's window-manager-facing EWMH 1.5 contract. The
canonical advertised set is `supportedAtomNames` in `internal/wm/atoms.go`;
`TestEWMHMatrixCoversRegistry` fails when this matrix and that registry drift.

Tags are represented as fixed EWMH desktops. The desktop count and names come
from the configured tag labels. The highest selected tag is the current
desktop; an all-tag window uses `0xffffffff`; any other multi-tag window uses
its highest tag. Assigning a desktop through EWMH replaces the internal tag set
with exactly that tag (or all tags). This mapping is intentionally lossy.

## Advertised root interface

| Area | Supported atoms and behavior |
|---|---|
| WM identity | `_NET_SUPPORTED`, `_NET_SUPPORTING_WM_CHECK`, `_NET_WM_NAME` |
| Clients | `_NET_CLIENT_LIST` in original manage order; `_NET_CLIENT_LIST_STACKING` bottom-to-top from the server's actual root/frame order |
| Desktops | `_NET_NUMBER_OF_DESKTOPS`, `_NET_DESKTOP_NAMES`, `_NET_DESKTOP_GEOMETRY`, zero `_NET_DESKTOP_VIEWPORT`, `_NET_CURRENT_DESKTOP`, per-desktop `_NET_WORKAREA` |
| Session state | `_NET_ACTIVE_WINDOW`, `_NET_SHOWING_DESKTOP` |

Desktop count and large-viewport requests are ignored as permitted by EWMH.
Runtime desktop-name changes are accepted until configuration is reloaded.

## Advertised requests

`_NET_ACTIVE_WINDOW`, `_NET_WM_DESKTOP`, `_NET_CLOSE_WINDOW`,
`_NET_MOVERESIZE_WINDOW`, `_NET_WM_MOVERESIZE`, `_NET_RESTACK_WINDOW`,
`_NET_REQUEST_FRAME_EXTENTS`, `_NET_SHOWING_DESKTOP`, `_NET_WM_STATE`, and
`_NET_WM_FULLSCREEN_MONITORS` (when Xinerama supplies monitor indices) are
implemented. Interactive moveresize supports eight edges, pointer and keyboard
move/resize, the declared terminating button, cancellation, and rollback.

Application activation requests require a non-stale X timestamp. Pager
requests are always accepted. Rejected requests set both
`_NET_WM_STATE_DEMANDS_ATTENTION` and ICCCM urgency.

## Advertised per-window interface

All standard `_NET_WM_WINDOW_TYPE_*` values are recognized. Desktop and dock
windows are undecorated and visible on every desktop; dialog, utility, toolbar,
menu, splash, dropdown, popup, tooltip, notification, combo, and DND types use
type-appropriate floating, focus, pager, and taskbar policy.

The following state atoms are implemented and canonicalized by the WM:

- `_NET_WM_STATE_MODAL`, `_NET_WM_STATE_STICKY`
- `_NET_WM_STATE_MAXIMIZED_VERT`, `_NET_WM_STATE_MAXIMIZED_HORZ`
- `_NET_WM_STATE_SHADED`, `_NET_WM_STATE_HIDDEN`
- `_NET_WM_STATE_SKIP_TASKBAR`, `_NET_WM_STATE_SKIP_PAGER`
- `_NET_WM_STATE_FULLSCREEN`, `_NET_WM_STATE_ABOVE`, `_NET_WM_STATE_BELOW`
- `_NET_WM_STATE_DEMANDS_ATTENTION`, `_NET_WM_STATE_FOCUSED`

`HIDDEN` and `FOCUSED` are read-only derived states. The obsolete
`_NET_WM_STATE_STAYS_ON_TOP` is accepted as an alias for `ABOVE`, but is never
advertised or written.

sadewm publishes `_NET_WM_DESKTOP`, `_NET_WM_STATE`,
`_NET_WM_ALLOWED_ACTIONS`, and `_NET_FRAME_EXTENTS` for every managed client.
It implements struts, user time and user-time windows, fullscreen monitor
selection, `_NET_WM_FULL_PLACEMENT`, and forwards `_NET_WM_WINDOW_OPACITY` to
reparenting frames without advertising that compositor-owned hint.

## Conditional protocols and extensions

| Facility | Condition | Behavior |
|---|---|---|
| `_NET_WM_FULLSCREEN_MONITORS` | Active Xinerama | Stable indices, topology refresh, largest-intersection reassignment, four-edge fullscreen spanning |
| `_NET_WM_SYNC_REQUEST` and `_NET_WM_SYNC_REQUEST_COUNTER` | XSync available | 64-bit counter values, coalesced interactive resize, acknowledgement polling, one-second fallback |
| RandR | Extension available | Screen/CRTC/output/provider/resource notifications trigger monitor topology rebuilds |
| `_NET_WM_PING` | Client lists it in `WM_PROTOCOLS` | Timestamped ping tracking, five-second unresponsive state, and force-kill only after another explicit close |

## ICCCM foundation

sadewm owns `WM_Sn`, sends the `MANAGER` announcement, exits on selection
loss, uses the save set for reparented clients, and supports `WM_CHANGE_STATE`,
`WM_STATE` Normal/Iconic/Withdrawn lifecycle, initial state, window groups,
transients, colormap windows, win gravity, `WM_TAKE_FOCUS`, `WM_DELETE_WINDOW`,
input models, and urgency. Genuine withdrawal removes WM-authored EWMH window
properties. Clean WM shutdown preserves takeover-relevant client properties
and removes all WM-authored root properties.

## Intentionally unadvertised or inapplicable

sadewm does not advertise virtual roots, scrolling desktops,
`_NET_DESKTOP_LAYOUT` (pager-owned), icon handling, handled-icons state,
compositor selection, opaque regions, or compositor bypass hints. Picom remains
the compositing manager; sadewm never claims `_NET_WM_CM_Sn`.

## Registry inventory

The unconditional `_NET_SUPPORTED` inventory is:

```text
_NET_SUPPORTED
_NET_CLIENT_LIST
_NET_CLIENT_LIST_STACKING
_NET_NUMBER_OF_DESKTOPS
_NET_DESKTOP_GEOMETRY
_NET_DESKTOP_VIEWPORT
_NET_CURRENT_DESKTOP
_NET_DESKTOP_NAMES
_NET_ACTIVE_WINDOW
_NET_WORKAREA
_NET_SUPPORTING_WM_CHECK
_NET_SHOWING_DESKTOP
_NET_CLOSE_WINDOW
_NET_MOVERESIZE_WINDOW
_NET_WM_MOVERESIZE
_NET_RESTACK_WINDOW
_NET_REQUEST_FRAME_EXTENTS
_NET_WM_NAME
_NET_WM_DESKTOP
_NET_WM_WINDOW_TYPE
_NET_WM_WINDOW_TYPE_DESKTOP
_NET_WM_WINDOW_TYPE_DOCK
_NET_WM_WINDOW_TYPE_TOOLBAR
_NET_WM_WINDOW_TYPE_MENU
_NET_WM_WINDOW_TYPE_UTILITY
_NET_WM_WINDOW_TYPE_SPLASH
_NET_WM_WINDOW_TYPE_DIALOG
_NET_WM_WINDOW_TYPE_DROPDOWN_MENU
_NET_WM_WINDOW_TYPE_POPUP_MENU
_NET_WM_WINDOW_TYPE_TOOLTIP
_NET_WM_WINDOW_TYPE_NOTIFICATION
_NET_WM_WINDOW_TYPE_COMBO
_NET_WM_WINDOW_TYPE_DND
_NET_WM_WINDOW_TYPE_NORMAL
_NET_WM_STATE
_NET_WM_STATE_MODAL
_NET_WM_STATE_STICKY
_NET_WM_STATE_MAXIMIZED_VERT
_NET_WM_STATE_MAXIMIZED_HORZ
_NET_WM_STATE_SHADED
_NET_WM_STATE_SKIP_TASKBAR
_NET_WM_STATE_SKIP_PAGER
_NET_WM_STATE_HIDDEN
_NET_WM_STATE_FULLSCREEN
_NET_WM_STATE_ABOVE
_NET_WM_STATE_BELOW
_NET_WM_STATE_DEMANDS_ATTENTION
_NET_WM_STATE_FOCUSED
_NET_WM_ALLOWED_ACTIONS
_NET_WM_ACTION_MOVE
_NET_WM_ACTION_RESIZE
_NET_WM_ACTION_MINIMIZE
_NET_WM_ACTION_SHADE
_NET_WM_ACTION_STICK
_NET_WM_ACTION_MAXIMIZE_HORZ
_NET_WM_ACTION_MAXIMIZE_VERT
_NET_WM_ACTION_FULLSCREEN
_NET_WM_ACTION_CHANGE_DESKTOP
_NET_WM_ACTION_CLOSE
_NET_WM_ACTION_ABOVE
_NET_WM_ACTION_BELOW
_NET_WM_STRUT
_NET_WM_STRUT_PARTIAL
_NET_WM_USER_TIME
_NET_WM_USER_TIME_WINDOW
_NET_FRAME_EXTENTS
_NET_WM_PING
_NET_WM_FULL_PLACEMENT
```

`_NET_WM_FULLSCREEN_MONITORS`, `_NET_WM_SYNC_REQUEST`, and
`_NET_WM_SYNC_REQUEST_COUNTER` are appended only under the extension conditions
listed above.
