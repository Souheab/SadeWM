"""BrightnessService — xrandr-based software brightness control."""

import subprocess
import re
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, Qt


class BrightnessService(QObject):
    _MIN_APPLY_INTERVAL = 0.05

    displaysChanged = Signal()
    _displaysReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._displays = []
        self._pending_set = {}
        self._set_running = False
        self._set_lock = threading.Lock()
        self._displaysReady.connect(
            self._set_displays, Qt.ConnectionType.QueuedConnection
        )
        self._list_displays()

    def _list_displays(self):
        def _run():
            try:
                result = subprocess.run(
                    ["xrandr", "--verbose"],
                    capture_output=True, text=True, timeout=5
                )
                displays = []
                current_output = None
                connected = False
                for line in result.stdout.splitlines():
                    m = re.match(r'^(\S+)\s+(connected|disconnected)', line)
                    if m:
                        current_output = m.group(1)
                        connected = m.group(2) == "connected"
                        continue
                    if connected and current_output:
                        bm = re.search(r'[Bb]rightness:\s*([0-9.]+)', line)
                        if bm:
                            displays.append({
                                "name": current_output,
                                "brightness": float(bm.group(1)),
                            })
                            current_output = None
                            connected = False
                self._displaysReady.emit(displays)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot(object)
    def _set_displays(self, displays):
        self._displays = displays
        self.displaysChanged.emit()

    @Property("QVariantList", notify=displaysChanged)
    def displays(self):
        return self._displays

    @Slot(str, float)
    def applyBrightness(self, name, value):
        """Queue the latest value for an output on a single xrandr worker."""
        v = max(0.05, min(1.0, value))
        with self._set_lock:
            self._pending_set[name] = v
            if self._set_running:
                return
            self._set_running = True
        threading.Thread(
            target=self._drain_brightness,
            daemon=True,
            name="sadeshell-brightness",
        ).start()

    def _drain_brightness(self):
        """Apply at most one command at a time, coalescing intermediate values."""
        last_apply = 0.0
        while True:
            with self._set_lock:
                if not self._pending_set:
                    self._set_running = False
                    return
                wait_for = max(
                    0.0,
                    last_apply + self._MIN_APPLY_INTERVAL - time.monotonic(),
                )
                if wait_for == 0:
                    pending = self._pending_set
                    self._pending_set = {}

            if wait_for:
                # Leave the pending dictionary in place while throttling so
                # drag updates continue replacing, rather than queueing, work.
                time.sleep(wait_for)
                continue

            for name, value in pending.items():
                try:
                    subprocess.run(
                        [
                            "xrandr", "--output", name,
                            "--brightness", f"{value:.3f}",
                        ],
                        timeout=5,
                    )
                except Exception:
                    pass
            last_apply = time.monotonic()

    @Slot(str, float)
    def setDisplay(self, name, value):
        """Optimistic update + xrandr. Use on release/click."""
        v = max(0.05, min(1.0, value))
        for i, d in enumerate(self._displays):
            if d["name"] == name:
                self._displays[i] = {**d, "brightness": v}
                self.displaysChanged.emit()
                break
        self.applyBrightness(name, v)
