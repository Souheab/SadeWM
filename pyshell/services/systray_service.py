"""SystrayService — StatusNotifier system tray host.

Implements org.kde.StatusNotifierWatcher (so apps can register tray icons even
on plain WMs that don't provide one) and acts as a StatusNotifierHost.

Items are exposed to QML as a QVariantList of dicts:
  {id, title, status, iconName, iconBase64, serviceName, objectPath}
"""

import threading
import asyncio
import base64
import struct
import logging

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, Qt
from PySide6.QtGui import QImage, QIcon, QPixmap
from PySide6.QtCore import QBuffer, QByteArray, QIODeviceBase

log = logging.getLogger(__name__)

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, signal as dbus_signal, dbus_property, PropertyAccess
    from dbus_next import Variant, BusType, DBusError
    from dbus_next.message import Message
    from dbus_next.constants import MessageType
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class _WatcherInterface(ServiceInterface if HAS_DBUS else object):
    """org.kde.StatusNotifierWatcher D-Bus service interface."""

    def __init__(self, service: "SystrayService"):
        if HAS_DBUS:
            super().__init__("org.kde.StatusNotifierWatcher")
        self._svc = service

    if HAS_DBUS:
        @method()
        def RegisterStatusNotifierItem(self, service: 's'):
            self._svc._on_item_registered(service)

        @method()
        def RegisterStatusNotifierHost(self, service: 's'):
            pass  # we are the host; other hosts welcome too

        @dbus_property(access=PropertyAccess.READ)
        def RegisteredStatusNotifierItems(self) -> 'as':
            return list(self._svc._item_services.keys())

        @dbus_property(access=PropertyAccess.READ)
        def IsStatusNotifierHostRegistered(self) -> 'b':
            return True

        @dbus_property(access=PropertyAccess.READ)
        def ProtocolVersion(self) -> 'i':
            return 0

        @dbus_signal()
        def StatusNotifierItemRegistered(self, service: 's'):
            pass

        @dbus_signal()
        def StatusNotifierItemUnregistered(self, service: 's'):
            pass

        @dbus_signal()
        def StatusNotifierHostRegistered(self):
            pass


def _argb_to_png_base64(width: int, height: int, data: bytes) -> str:
    """Convert ARGB32 network-byte-order pixel data to base64-encoded PNG."""
    try:
        n = width * height
        raw = bytes(data)
        if len(raw) < n * 4:
            return ""
        # Network ARGB: each pixel is [A, R, G, B]
        # QImage.Format_ARGB32 on any endian wants 0xAARRGGBB 32-bit integers
        # We can do a byte-swap to produce BGRA (which is Format_ARGB32 on LE)
        rgba = bytearray(n * 4)
        for i in range(n):
            a = raw[i * 4]
            r = raw[i * 4 + 1]
            g = raw[i * 4 + 2]
            b = raw[i * 4 + 3]
            rgba[i * 4]     = b  # B
            rgba[i * 4 + 1] = g  # G
            rgba[i * 4 + 2] = r  # R
            rgba[i * 4 + 3] = a  # A
        img = QImage(bytes(rgba), width, height, width * 4, QImage.Format.Format_ARGB32)
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return base64.b64encode(buf.data().data()).decode()
    except Exception as e:
        log.debug("_argb_to_png_base64 error: %s", e)
        return ""


def _icon_name_to_base64(icon_name: str, size: int = 24) -> str:
    """Resolve an XDG icon name and encode to base64 PNG. Returns '' on failure."""
    try:
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            return ""
        pixmap = icon.pixmap(size, size)
        if pixmap.isNull():
            return ""
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        return base64.b64encode(buf.data().data()).decode()
    except Exception:
        return ""


class SystrayService(QObject):
    itemsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []        # items exposed to QML
        self._item_services: dict[str, dict] = {}  # key=service_id, val=raw data
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus = None
        self._watcher_iface: _WatcherInterface | None = None

        if HAS_DBUS:
            self._start_loop()

    # ── background asyncio thread ──────────────────────────────────────────────

    def _start_loop(self):
        def _run():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._serve())
            except Exception as e:
                log.warning("SystrayService loop error: %s", e)
        threading.Thread(target=_run, daemon=True, name="systray-dbus").start()

    async def _serve(self):
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

        # Try to claim the watcher name; if already taken, we still watch it.
        self._watcher_iface = _WatcherInterface(self)
        self._bus.export("/StatusNotifierWatcher", self._watcher_iface)

        try:
            await self._bus.request_name("org.kde.StatusNotifierWatcher")
            log.info("SystrayService: registered as StatusNotifierWatcher")
        except DBusError:
            log.info("SystrayService: StatusNotifierWatcher already exists — using existing watcher")

        # Register ourselves as a host with the watcher (may be ours or external).
        try:
            reply = await self._bus.call(
                Message(
                    destination="org.kde.StatusNotifierWatcher",
                    path="/StatusNotifierWatcher",
                    interface="org.kde.StatusNotifierWatcher",
                    member="RegisterStatusNotifierHost",
                    signature="s",
                    body=[self._bus.unique_name],
                )
            )
        except Exception as e:
            log.debug("RegisterStatusNotifierHost: %s", e)

        # Watch for new/removed items on the watcher.
        self._bus.add_message_handler(self._handle_message)

        # Subscribe to NameOwnerChanged so we can remove items when their owner dies.
        await self._bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',interface='org.kde.StatusNotifierWatcher'"],
            )
        )
        await self._bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged'"],
            )
        )

        # Fetch any items already registered with the existing watcher.
        try:
            reply = await self._bus.call(
                Message(
                    destination="org.kde.StatusNotifierWatcher",
                    path="/StatusNotifierWatcher",
                    interface="org.freedesktop.DBus.Properties",
                    member="Get",
                    signature="ss",
                    body=["org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems"],
                )
            )
            if reply.body:
                existing = reply.body[0].value if hasattr(reply.body[0], 'value') else reply.body[0]
                for svc in (existing or []):
                    asyncio.ensure_future(self._register_item(svc))
        except Exception as e:
            log.debug("Fetch existing items: %s", e)

        await self._bus.wait_for_disconnect()

    def _handle_message(self, message) -> bool:
        if not hasattr(message, 'interface'):
            return False
        if message.message_type != MessageType.SIGNAL:
            return False

        iface = message.interface or ""
        member = message.member or ""

        if iface == "org.kde.StatusNotifierWatcher":
            if member == "StatusNotifierItemRegistered" and message.body:
                svc_id = message.body[0]
                asyncio.ensure_future(self._register_item(svc_id))
            elif member == "StatusNotifierItemUnregistered" and message.body:
                self._remove_item(message.body[0])
        elif iface == "org.freedesktop.DBus" and member == "NameOwnerChanged":
            if len(message.body) >= 3:
                name, old_owner, new_owner = message.body[:3]
                if new_owner == "" and old_owner != "":
                    self._remove_items_by_owner(old_owner)
        elif iface == "org.kde.StatusNotifierItem":
            if member in ("NewIcon", "NewTitle", "NewStatus", "NewToolTip"):
                # Find which service this is from and refresh it
                sender = message.sender or ""
                if sender in self._item_services:
                    asyncio.ensure_future(self._refresh_item(sender))
        return False

    # Called from our own Watcher interface when WE are the watcher.
    def _on_item_registered(self, service: str):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._register_item(service), self._loop)

    async def _register_item(self, service_id: str):
        """Fetch properties from a newly registered StatusNotifierItem."""
        # service_id may be "org.kde.foo-1234" or "org.kde.foo-1234/CustomPath"
        if "/" in service_id:
            service_name, obj_path = service_id.split("/", 1)
            obj_path = "/" + obj_path
        else:
            service_name = service_id
            obj_path = "/StatusNotifierItem"

        try:
            intr = await self._bus.introspect(service_name, obj_path)
            proxy = self._bus.get_proxy_object(service_name, obj_path, intr)

            # Try both known SNI interface namespaces.
            sni_iface = None
            for iface_name in ("org.kde.StatusNotifierItem", "org.freedesktop.StatusNotifierItem"):
                try:
                    sni_iface = proxy.get_interface(iface_name)
                    break
                except Exception:
                    pass

            if sni_iface is None:
                return

            # Read properties individually, tolerating missing ones.
            async def _get(attr, default=""):
                try:
                    return await getattr(sni_iface, "get_" + attr.lower())()
                except Exception:
                    return default

            title      = await _get("Title") or ""
            status     = await _get("Status") or "Active"
            icon_name  = await _get("IconName") or ""
            try:
                icon_pixmap = await sni_iface.get_icon_pixmap()
            except Exception:
                icon_pixmap = []

            # Build base64 icon
            icon_b64 = ""
            if icon_name:
                icon_b64 = _icon_name_to_base64(icon_name)
            if not icon_b64 and icon_pixmap:
                try:
                    best = max(icon_pixmap, key=lambda p: p[0] * p[1])
                    icon_b64 = _argb_to_png_base64(best[0], best[1], best[2])
                except Exception:
                    pass

            item_data = {
                "id": service_id,
                "title": title,
                "status": status,
                "iconName": icon_name,
                "iconBase64": icon_b64,
                "serviceName": service_name,
                "objectPath": obj_path,
            }

            self._item_services[service_id] = item_data
            self._flush_items()

            # Subscribe to updates from this item.
            await self._bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="AddMatch",
                    signature="s",
                    body=[
                        f"type='signal',sender='{service_name}',"
                        f"path='{obj_path}',interface='org.kde.StatusNotifierItem'"
                    ],
                )
            )

        except Exception as e:
            log.debug("_register_item(%s): %s", service_id, e)

    async def _refresh_item(self, service_id: str):
        """Re-fetch properties for an already-registered item."""
        if service_id in self._item_services:
            await self._register_item(service_id)

    def _remove_item(self, service_id: str):
        if service_id in self._item_services:
            del self._item_services[service_id]
            self._flush_items()

    def _remove_items_by_owner(self, owner: str):
        to_remove = [k for k in self._item_services
                     if k == owner or k.startswith(owner + "/")]
        for k in to_remove:
            del self._item_services[k]
        if to_remove:
            self._flush_items()

    def _flush_items(self):
        """Update the QML-exposed list on the GUI thread."""
        new_items = [
            v for v in self._item_services.values()
            if v.get("status", "Active") != "Passive"
        ]
        # Post via Qt signal to stay thread-safe.
        self._items = new_items
        self.itemsChanged.emit()

    # ── QML/Slot interface ─────────────────────────────────────────────────────

    @Property("QVariantList", notify=itemsChanged)
    def items(self):
        return self._items

    @Slot(str, int, int)
    def activate(self, service_id: str, x: int, y: int):
        """Send Activate to the item (left-click action)."""
        if not self._loop or service_id not in self._item_services:
            return
        data = self._item_services[service_id]
        async def _do():
            try:
                await self._bus.call(
                    Message(
                        destination=data["serviceName"],
                        path=data["objectPath"],
                        interface="org.kde.StatusNotifierItem",
                        member="Activate",
                        signature="ii",
                        body=[x, y],
                    )
                )
            except Exception as e:
                log.debug("activate: %s", e)
        asyncio.run_coroutine_threadsafe(_do(), self._loop)

    @Slot(str, int, int)
    def contextMenu(self, service_id: str, x: int, y: int):
        """Send ContextMenu to the item (right-click action)."""
        if not self._loop or service_id not in self._item_services:
            return
        data = self._item_services[service_id]
        async def _do():
            try:
                await self._bus.call(
                    Message(
                        destination=data["serviceName"],
                        path=data["objectPath"],
                        interface="org.kde.StatusNotifierItem",
                        member="ContextMenu",
                        signature="ii",
                        body=[x, y],
                    )
                )
            except Exception as e:
                log.debug("contextMenu: %s", e)
        asyncio.run_coroutine_threadsafe(_do(), self._loop)
