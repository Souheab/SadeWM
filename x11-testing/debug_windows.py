#!/usr/bin/env python3
"""Debug script to inspect window positions and pointer query results."""
import os
os.environ.setdefault("DISPLAY", ":98")

from Xlib import display, X

d = display.Display()
r = d.screen().root

# Get managed windows
atom = d.intern_atom("_NET_CLIENT_LIST")
prop = r.get_full_property(atom, X.AnyPropertyType)
wids = list(prop.value) if prop else []
print(f"Managed windows: {[hex(w) for w in wids]}")

for wid in wids:
    w = d.create_resource_object("window", wid)
    g = w.get_geometry()
    try:
        t = w.translate_coords(r, 0, 0)
        print(f"  0x{wid:x}: geom=({g.x},{g.y}) {g.width}x{g.height}, translate=({-t.x},{-t.y}), border={g.border_width}")
    except Exception as e:
        print(f"  0x{wid:x}: geom=({g.x},{g.y}) {g.width}x{g.height}, translate_err={e}")
    attrs = w.get_attributes()
    print(f"          map_state={attrs.map_state} override={attrs.override_redirect}")

# Pointer
q = r.query_pointer()
print(f"\nPointer: ({q.root_x},{q.root_y}), child=0x{q.child.id if q.child else 0:x}")

# Move pointer to center of first window and query again
import time
r.warp_pointer(200, 400)
d.flush()
time.sleep(0.1)
q2 = r.query_pointer()
print(f"Pointer at (200,400): child=0x{q2.child.id if q2.child else 0:x}")

r.warp_pointer(800, 400)
d.flush()
time.sleep(0.1)
q3 = r.query_pointer()
print(f"Pointer at (800,400): child=0x{q3.child.id if q3.child else 0:x}")

# Root children
print("\nRoot children:")
for c in r.query_tree().children:
    g = c.get_geometry()
    attrs = c.get_attributes()
    name = c.get_wm_name() or ""
    ms = "mapped" if attrs.map_state == 2 else f"state={attrs.map_state}"
    print(f"  0x{c.id:x}: ({g.x},{g.y}) {g.width}x{g.height} bw={g.border_width} {ms} name={name}")

d.close()
