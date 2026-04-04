"""BrightnessService — xrandr-based software brightness control."""

import subprocess
import re
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot


class BrightnessService(QObject):
    displaysChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._displays = []
        self._pending_set = None
        self._set_running = False
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
                self._displays = displays
                self.displaysChanged.emit()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Property("QVariantList", notify=displaysChanged)
    def displays(self):
        return self._displays

    @Slot(str, float)
    def applyBrightness(self, name, value):
        """Fire xrandr — does NOT update local state. Safe at 60fps."""
        v = max(0.05, min(1.0, value))
        vs = f"{v:.3f}"

        def _run():
            try:
                subprocess.run(
                    ["xrandr", "--output", name, "--brightness", vs],
                    timeout=5
                )
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

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
