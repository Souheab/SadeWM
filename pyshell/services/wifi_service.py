"""WiFiService — NetworkManager WiFi control via nmcli."""

import subprocess
import json
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer


class WiFiService(QObject):
    wifiEnabledChanged = Signal()
    connectedSsidChanged = Signal()
    connectedSignalChanged = Signal()
    networksChanged = Signal()
    scanningChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wifi_enabled = False
        self._connected_ssid = ""
        self._connected_signal = 0
        self._networks = []
        self._scanning = False

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(10000)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start()
        self._poll_status()

    def _poll_status(self):
        def _run():
            try:
                radio = subprocess.run(
                    ["nmcli", "radio", "wifi"],
                    capture_output=True, text=True, timeout=5
                )
                enabled = radio.stdout.strip().lower() == "enabled"

                ssid = ""
                sig = 0
                if enabled:
                    dev = subprocess.run(
                        ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in dev.stdout.strip().splitlines():
                        rparts = line.rsplit(":", 1)
                        if len(rparts) == 2:
                            left, signal_str = rparts
                            lparts = left.split(":", 1)
                            if len(lparts) == 2 and lparts[0] == "yes":
                                ssid = lparts[1].replace("\\:", ":")
                                sig = int(signal_str) if signal_str.isdigit() else 0
                                break

                if enabled != self._wifi_enabled:
                    self._wifi_enabled = enabled
                    self.wifiEnabledChanged.emit()
                if ssid != self._connected_ssid:
                    self._connected_ssid = ssid
                    self.connectedSsidChanged.emit()
                if sig != self._connected_signal:
                    self._connected_signal = sig
                    self.connectedSignalChanged.emit()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Property(bool, notify=wifiEnabledChanged)
    def wifiEnabled(self):
        return self._wifi_enabled

    @Property(str, notify=connectedSsidChanged)
    def connectedSsid(self):
        return self._connected_ssid

    @Property(int, notify=connectedSignalChanged)
    def connectedSignal(self):
        return self._connected_signal

    @Property("QVariantList", notify=networksChanged)
    def networks(self):
        return self._networks

    @Property(bool, notify=scanningChanged)
    def scanning(self):
        return self._scanning

    def _list_networks(self, rescan=False):
        def _run():
            try:
                if rescan:
                    subprocess.run(
                        ["nmcli", "dev", "wifi", "rescan"],
                        capture_output=True, timeout=10
                    )
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi", "list", "--rescan", "no"],
                    capture_output=True, text=True, timeout=5
                )
                networks = []
                seen = set()
                for line in result.stdout.strip().splitlines():
                    if not line:
                        continue
                    parts = line.rsplit(":", 3)
                    if len(parts) < 4:
                        continue
                    ssid_raw, signal_str, security, active = parts
                    ssid = ssid_raw.replace("\\:", ":")
                    if not ssid or ssid in seen:
                        continue
                    seen.add(ssid)
                    sig = int(signal_str) if signal_str.isdigit() else 0
                    networks.append({
                        "ssid": ssid,
                        "signal": sig,
                        "secure": bool(security.strip()),
                        "active": active.strip().lower() == "yes",
                    })
                networks.sort(key=lambda n: (not n["active"], -n["signal"]))
                self._networks = networks
                self.networksChanged.emit()
            except Exception:
                pass
            finally:
                if self._scanning:
                    self._scanning = False
                    self.scanningChanged.emit()
                self._poll_status()
        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scanningChanged.emit()
        self._list_networks(rescan=True)

    @Slot()
    def refreshList(self):
        self._list_networks(rescan=False)

    @Slot()
    def toggleWifi(self):
        def _run():
            try:
                radio = subprocess.run(
                    ["nmcli", "radio", "wifi"],
                    capture_output=True, text=True, timeout=5
                )
                if radio.stdout.strip().lower() == "enabled":
                    subprocess.run(["nmcli", "radio", "wifi", "off"], timeout=5)
                else:
                    subprocess.run(["nmcli", "radio", "wifi", "on"], timeout=5)
            except Exception:
                pass
            self._poll_status()
        threading.Thread(target=_run, daemon=True).start()

    @Slot(str)
    def connectTo(self, ssid):
        def _run():
            try:
                subprocess.run(
                    ["nmcli", "device", "wifi", "connect", ssid],
                    timeout=30
                )
            except Exception:
                pass
            self._poll_status()
        threading.Thread(target=_run, daemon=True).start()
