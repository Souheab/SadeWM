"""BluetoothService — BlueZ Bluetooth control via bluetoothctl / dbus-next."""

import threading
import asyncio
import subprocess

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

try:
    from dbus_next.aio import MessageBus
    from dbus_next import BusType, Variant
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class BluetoothService(QObject):
    enabledChanged = Signal()
    devicesChanged = Signal()
    scanningChanged = Signal()
    connectedDeviceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._devices = []          # list of dicts: {name, address, connected, paired, icon}
        self._scanning = False
        self._connected_device = ""

        # Fast poll via bluetoothctl
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(8000)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()
        self._poll()

    # ── polling ────────────────────────────────────────────────────────────────

    def _poll(self):
        def _run():
            try:
                # Check powered state
                show = subprocess.run(
                    ["bluetoothctl", "show"],
                    capture_output=True, text=True, timeout=5
                )
                powered = False
                for line in show.stdout.splitlines():
                    if "Powered:" in line:
                        powered = "yes" in line.lower()
                        break

                # List devices (paired)
                devs_out = subprocess.run(
                    ["bluetoothctl", "devices", "Paired"],
                    capture_output=True, text=True, timeout=5
                )
                devices = []
                connected_name = ""
                for line in devs_out.stdout.strip().splitlines():
                    parts = line.split(" ", 2)
                    if len(parts) < 3 or parts[0] != "Device":
                        continue
                    addr = parts[1]
                    name = parts[2]
                    # Check if connected
                    info = subprocess.run(
                        ["bluetoothctl", "info", addr],
                        capture_output=True, text=True, timeout=3
                    )
                    connected = False
                    icon = "audio-card"
                    for iline in info.stdout.splitlines():
                        if "Connected: yes" in iline:
                            connected = True
                        if "Icon:" in iline:
                            icon = iline.split("Icon:")[1].strip()
                    if connected:
                        connected_name = name
                    devices.append({
                        "name": name,
                        "address": addr,
                        "connected": connected,
                        "icon": icon,
                    })

                if powered != self._enabled:
                    self._enabled = powered
                    self.enabledChanged.emit()
                if devices != self._devices:
                    self._devices = devices
                    self.devicesChanged.emit()
                if connected_name != self._connected_device:
                    self._connected_device = connected_name
                    self.connectedDeviceChanged.emit()
            except FileNotFoundError:
                # bluetoothctl not installed
                pass
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    # ── properties ─────────────────────────────────────────────────────────────

    @Property(bool, notify=enabledChanged)
    def enabled(self):
        return self._enabled

    @Property("QVariantList", notify=devicesChanged)
    def devices(self):
        return self._devices

    @Property(bool, notify=scanningChanged)
    def scanning(self):
        return self._scanning

    @Property(str, notify=connectedDeviceChanged)
    def connectedDevice(self):
        return self._connected_device

    # ── slots ──────────────────────────────────────────────────────────────────

    @Slot()
    def toggleBluetooth(self):
        def _run():
            try:
                cmd = "off" if self._enabled else "on"
                subprocess.run(
                    ["bluetoothctl", "power", cmd],
                    capture_output=True, timeout=5
                )
                self._poll()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def startScan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scanningChanged.emit()

        def _run():
            try:
                subprocess.run(
                    ["bluetoothctl", "--timeout", "8", "scan", "on"],
                    capture_output=True, timeout=12
                )
            except Exception:
                pass
            finally:
                self._scanning = False
                self.scanningChanged.emit()
                self._poll()
        threading.Thread(target=_run, daemon=True).start()

    @Slot(str)
    def connectDevice(self, address):
        def _run():
            try:
                subprocess.run(
                    ["bluetoothctl", "connect", address],
                    capture_output=True, timeout=10
                )
                self._poll()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot(str)
    def disconnectDevice(self, address):
        def _run():
            try:
                subprocess.run(
                    ["bluetoothctl", "disconnect", address],
                    capture_output=True, timeout=10
                )
                self._poll()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def refresh(self):
        self._poll()
