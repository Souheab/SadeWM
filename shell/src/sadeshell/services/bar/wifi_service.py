"""NetworkManager subscriptions; nmcli is used only for user-requested connections."""
import asyncio

from dbus_next import Variant
from PySide6.QtCore import Property, Signal, Slot

from ..shared.async_bus import AsyncService, ObjectMonitor, PROPS

NM = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
WIRELESS = NM + ".Device.Wireless"
AP = NM + ".AccessPoint"


def network_rows(objects):
    active = {interfaces[WIRELESS].get("ActiveAccessPoint") for interfaces in objects.values() if WIRELESS in interfaces}
    by_ssid = {}
    for path, interfaces in objects.items():
        if AP not in interfaces:
            continue
        ap = interfaces[AP]
        ssid = bytes(ap.get("Ssid", [])).decode("utf-8", "replace")
        if not ssid:
            continue
        row = dict(ssid=ssid, signal=ap.get("Strength", 0),
                   secure=bool(ap.get("Flags", 0) & 1 or ap.get("WpaFlags") or ap.get("RsnFlags")),
                   active=path in active)
        previous = by_ssid.get(ssid)
        if previous is None or (row["active"], row["signal"]) > (previous["active"], previous["signal"]):
            by_ssid[ssid] = row
    return sorted(by_ssid.values(), key=lambda row: (not row["active"], -row["signal"], row["ssid"]))


class WiFiService(AsyncService):
    wifiEnabledChanged = Signal()
    connectedSsidChanged = Signal()
    connectedSignalChanged = Signal()
    networksChanged = Signal()
    scanningChanged = Signal()
    _scanDone = Signal()

    def __init__(self, parent=None, worker=None):
        super().__init__(parent, worker)
        self._wifi_enabled = False
        self._connected_ssid = ""
        self._connected_signal = 0
        self._networks = []
        self._scanning = False
        self.monitor = ObjectMonitor(self, NM, "/org/freedesktop")
        self._scanDone.connect(self._finish_scan)
        self.start_task(self.monitor.run())

    wifiEnabled = Property(bool, lambda self: self._wifi_enabled, notify=wifiEnabledChanged)
    connectedSsid = Property(str, lambda self: self._connected_ssid, notify=connectedSsidChanged)
    connectedSignal = Property(int, lambda self: self._connected_signal, notify=connectedSignalChanged)
    networks = Property("QVariantList", lambda self: self._networks, notify=networksChanged)
    scanning = Property(bool, lambda self: self._scanning, notify=scanningChanged)

    def apply_state(self, objects):
        rows = network_rows(objects)
        connected = next((r for r in rows if r["active"]), {})
        for field, value, signal in (
            ("_wifi_enabled", bool(objects.get(ROOT, {}).get(NM, {}).get("WirelessEnabled")), self.wifiEnabledChanged),
            ("_connected_ssid", connected.get("ssid", ""), self.connectedSsidChanged),
            ("_connected_signal", connected.get("signal", 0), self.connectedSignalChanged),
            ("_networks", rows, self.networksChanged),
        ):
            if getattr(self, field) != value:
                setattr(self, field, value)
                signal.emit()

    @Slot()
    def toggleWifi(self):
        enabled = not self._wifi_enabled
        self.command(self.monitor.invoke(ROOT, PROPS, "Set", "ssv",
                                         [NM, "WirelessEnabled", Variant("b", enabled)]), "adapter")

    @Slot()
    def refreshList(self):
        # The subscription keeps the catalogue current, including while closed.
        pass

    @Slot()
    def scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scanningChanged.emit()

        async def scan():
            try:
                devices = {p: v[WIRELESS].get("LastScan") for p, v in self.monitor.objects.items() if WIRELESS in v}
                if not devices:
                    raise RuntimeError("No Wi-Fi adapter is available")
                for path in devices:
                    await self.monitor.invoke(path, WIRELESS, "RequestScan", "a{sv}", [{}])
                async with asyncio.timeout(20):
                    while any(self.monitor.objects.get(p, {}).get(WIRELESS, {}).get("LastScan") == old for p, old in devices.items()):
                        self.monitor.changed.clear()
                        await self.monitor.changed.wait()
            finally:
                self._scanDone.emit()
        self.command(scan(), "adapter")

    @Slot()
    def _finish_scan(self):
        self._scanning = False
        self.scanningChanged.emit()

    @Slot(str)
    def connectTo(self, ssid):
        async def connect():
            process = await asyncio.create_subprocess_exec(
                "nmcli", "device", "wifi", "connect", ssid,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), 30)
                if process.returncode:
                    raise RuntimeError(stderr.decode(errors="replace").strip() or "Wi-Fi connection failed")
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
        self.command(connect(), "adapter")
