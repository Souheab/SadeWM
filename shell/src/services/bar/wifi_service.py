"""WiFiService — NetworkManager WiFi control via nmcli."""

import subprocess
import json
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, Qt


class WiFiService(QObject):
    wifiEnabledChanged = Signal()
    connectedSsidChanged = Signal()
    connectedSignalChanged = Signal()
    networksChanged = Signal()
    scanningChanged = Signal()
    _statusReady = Signal(object)
    _statusRequested = Signal()
    _networksReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wifi_enabled = False
        self._connected_ssid = ""
        self._connected_signal = 0
        self._networks = []
        self._scanning = False
        self._status_running = False
        self._status_pending = False
        self._list_running = False
        self._list_pending = False
        self._list_pending_rescan = False

        self._statusReady.connect(
            self._finish_status_poll, Qt.ConnectionType.QueuedConnection
        )
        self._statusRequested.connect(
            self._poll_status, Qt.ConnectionType.QueuedConnection
        )
        self._networksReady.connect(
            self._finish_network_list, Qt.ConnectionType.QueuedConnection
        )

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(10000)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start()
        self._poll_status()

    def _poll_status(self):
        if self._status_running:
            self._status_pending = True
            return
        self._status_running = True

        def _run():
            state = None
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

                state = (enabled, ssid, sig)
            except Exception:
                pass
            self._statusReady.emit(state)
        threading.Thread(
            target=_run, daemon=True, name="sadeshell-wifi-status"
        ).start()

    @Slot(object)
    def _finish_status_poll(self, state):
        self._status_running = False
        if state is not None:
            enabled, ssid, sig = state
            if enabled != self._wifi_enabled:
                self._wifi_enabled = enabled
                self.wifiEnabledChanged.emit()
            if ssid != self._connected_ssid:
                self._connected_ssid = ssid
                self.connectedSsidChanged.emit()
            if sig != self._connected_signal:
                self._connected_signal = sig
                self.connectedSignalChanged.emit()
        if self._status_pending:
            self._status_pending = False
            self._poll_status()

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
        if self._list_running:
            self._list_pending = True
            self._list_pending_rescan = self._list_pending_rescan or rescan
            return
        self._list_running = True

        def _run():
            networks = None
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
            except Exception:
                pass
            finally:
                self._networksReady.emit((networks, rescan))
        threading.Thread(
            target=_run, daemon=True, name="sadeshell-wifi-networks"
        ).start()

    @Slot(object)
    def _finish_network_list(self, payload):
        networks, was_rescan = payload
        self._list_running = False
        if networks is not None and networks != self._networks:
            self._networks = networks
            self.networksChanged.emit()
        if was_rescan and self._scanning:
            self._scanning = False
            self.scanningChanged.emit()
        self._poll_status()
        if self._list_pending:
            rescan = self._list_pending_rescan
            self._list_pending = False
            self._list_pending_rescan = False
            self._list_networks(rescan=rescan)

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
        enabled = self._wifi_enabled

        def _run():
            try:
                if enabled:
                    subprocess.run(["nmcli", "radio", "wifi", "off"], timeout=5)
                else:
                    subprocess.run(["nmcli", "radio", "wifi", "on"], timeout=5)
            except Exception:
                pass
            self._statusRequested.emit()
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
            self._statusRequested.emit()
        threading.Thread(target=_run, daemon=True).start()
