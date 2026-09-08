"""BlueZ ObjectManager subscriptions and asynchronous adapter/device commands."""
import asyncio

from dbus_next import Variant
from PySide6.QtCore import Property, Signal, Slot

from ..shared.async_bus import AsyncService, ObjectMonitor, PROPS

ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"


class BluetoothService(AsyncService):
    enabledChanged = Signal()
    devicesChanged = Signal()
    scanningChanged = Signal()
    connectedDeviceChanged = Signal()
    _scanDone = Signal()

    def __init__(self, parent=None, worker=None):
        super().__init__(parent, worker)
        self._enabled = False
        self._devices = []
        self._scanning = False
        self._connected_device = ""
        self.monitor = ObjectMonitor(self, "org.bluez", "/")
        self._scanDone.connect(self._finish_scan)
        self.start_task(self.monitor.run())

    enabled = Property(bool, lambda self: self._enabled, notify=enabledChanged)
    devices = Property("QVariantList", lambda self: self._devices, notify=devicesChanged)
    scanning = Property(bool, lambda self: self._scanning, notify=scanningChanged)
    connectedDevice = Property(str, lambda self: self._connected_device, notify=connectedDeviceChanged)

    def apply_state(self, objects):
        powered = any(v.get(ADAPTER, {}).get("Powered", False) for v in objects.values())
        devices = []
        for interfaces in objects.values():
            if DEVICE not in interfaces:
                continue
            props = interfaces[DEVICE]
            devices.append(dict(name=props.get("Alias", props.get("Name", props.get("Address", ""))),
                                address=props.get("Address", ""), connected=props.get("Connected", False),
                                paired=props.get("Paired", False), icon=props.get("Icon", "audio-card")))
        devices.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"], d["address"]))
        connected = next((d["name"] for d in devices if d["connected"]), "")
        for field, value, signal in (("_enabled", powered, self.enabledChanged),
                                     ("_devices", devices, self.devicesChanged),
                                     ("_connected_device", connected, self.connectedDeviceChanged)):
            if getattr(self, field) != value:
                setattr(self, field, value)
                signal.emit()

    def _adapter(self):
        path = next((p for p, v in self.monitor.objects.items() if ADAPTER in v), None)
        if not path:
            raise RuntimeError("No Bluetooth adapter is available")
        return path

    @Slot()
    def toggleBluetooth(self):
        enabled = not self._enabled
        async def toggle():
            await self.monitor.invoke(self._adapter(), PROPS, "Set", "ssv",
                                      [ADAPTER, "Powered", Variant("b", enabled)])
        self.command(toggle(), "adapter")

    @Slot()
    def startScan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scanningChanged.emit()
        async def scan():
            path = None
            try:
                path = self._adapter()
                await self.monitor.invoke(path, ADAPTER, "StartDiscovery")
                await asyncio.sleep(8)
            finally:
                try:
                    if path:
                        await self.monitor.invoke(path, ADAPTER, "StopDiscovery")
                finally:
                    self._scanDone.emit()
        self.command(scan(), "adapter")

    @Slot()
    def _finish_scan(self):
        self._scanning = False
        self.scanningChanged.emit()

    def _device_command(self, address, member):
        async def run():
            path = next((p for p, v in self.monitor.objects.items() if v.get(DEVICE, {}).get("Address") == address), None)
            if not path:
                raise RuntimeError("Bluetooth device is no longer available")
            await self.monitor.invoke(path, DEVICE, member)
        self.command(run(), address)

    @Slot(str)
    def connectDevice(self, address):
        self._device_command(address, "Connect")

    @Slot(str)
    def disconnectDevice(self, address):
        self._device_command(address, "Disconnect")

    @Slot()
    def refresh(self):
        pass
