"""Release WM comparison on private Xvfb servers; outputs measured data, not thresholds."""
import argparse
import collections
import json
import os
from pathlib import Path
import platform
import statistics
import tempfile
import time

from Xlib import X
from Xlib.ext import res  # noqa: F401 -- registers the XRes methods
from test_parity import card, desktop, request


def ticks(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def rss(pid):
    return int(next(line.split()[1] for line in Path(f"/proc/{pid}/status").read_text().splitlines() if line.startswith("VmRSS:")))


def measure(binary, directory, count, floating=False):
    with desktop(binary, directory, debug=False) as (xd, sock, process, env):
        dpy = xd._xdisplay
        root = dpy.screen().root
        root.warp_pointer(0, 0)
        owner = card(xd, root, "_NET_SUPPORTING_WM_CHECK")[0]
        def resources():
            dpy.sync()
            return {dpy.get_atom_name(row.resource_type): row.count for row in dpy.res_query_client_resources(owner).types if row.count}
        baseline = resources()
        memory_empty = rss(process.pid)
        windows = [xd.new_window(title=f"benchmark-{i}", size=(400, 260), **({"type": "dialog"} if floating else {})) for i in range(count)]
        xd.wait_for_layout()
        memory_loaded = rss(process.pid)
        start_ticks = ticks(process.pid)
        start = time.monotonic()
        time.sleep(3)
        idle = (ticks(process.pid) - start_ticks) / os.sysconf("SC_CLK_TCK") / (time.monotonic() - start) * 100
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            request(sock, "get_state")
            latencies.append((time.perf_counter() - start) * 1000)
        root.change_attributes(event_mask=X.PropertyChangeMask)
        for win in windows:
            win._xwindow.change_attributes(event_mask=X.PropertyChangeMask)
        dpy.sync()
        while dpy.pending_events():
            dpy.next_event()
        focuses = []
        for i in range(100):
            start = time.perf_counter()
            request(sock, "focus_window", win_id=windows[i % count].id)
            assert dpy.get_input_focus().focus.id == windows[i % count].id
            focuses.append((time.perf_counter() - start) * 1000)
        writes = collections.Counter()
        dpy.sync()
        while dpy.pending_events():
            ev = dpy.next_event()
            if ev.type == X.PropertyNotify:
                writes[dpy.get_atom_name(ev.atom)] += 1
        assert writes["_NET_CLIENT_LIST"] == 0
        assert writes["_NET_CURRENT_DESKTOP"] == 0
        assert writes["_NET_ACTIVE_WINDOW"] == 100
        assert writes["_NET_WM_STATE"] <= 202
        for win in windows:
            win.kill()
        xd.wait_for_layout()
        after = resources()
        assert after == baseline, (baseline, after)
        def distribution(values):
            return {"p50_ms": round(statistics.median(values), 3), "p95_ms": round(sorted(values)[94], 3)}
        return {"windows": count, "layout": "floating" if floating else "tiled", "rss_empty_kib": memory_empty, "rss_loaded_kib": memory_loaded,
                "rss_after_cleanup_kib": rss(process.pid), "idle_cpu_percent": round(idle, 3),
                "ipc": distribution(latencies), "focus": distribution(focuses),
                "property_writes_100_focuses": dict(writes), "resources_before": baseline,
                "resources_after": after, "threads": len(list(Path(f"/proc/{process.pid}/task").iterdir())),
                "fds": len(list(Path(f"/proc/{process.pid}/fd").iterdir()))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--go", required=True)
    parser.add_argument("--rust", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sadewm-benchmark-") as temporary:
        results = {"environment": platform.platform(), "idle_seconds": 3,
                   "note": "Single local run; Xvfb, release binaries, debug logging disabled. Not a hardware or compositor performance claim."}
        for name, binary in (("go", args.go), ("rust", args.rust)):
            results[name] = [measure(binary, Path(temporary) / f"{name}-{n}-{floating}", n, floating)
                             for floating in (False, True) for n in (1, 20)]
    Path(args.output).write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
