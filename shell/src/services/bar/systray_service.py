"""StatusNotifier/AppIndicator system tray host for sadeshell."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QIcon, QImage
from PySide6.QtCore import QBuffer, QIODeviceBase

log = logging.getLogger(__name__)

try:
    from dbus_next import BusType, DBusError, Variant
    from dbus_next.aio import MessageBus
    from dbus_next.constants import MessageType
    from dbus_next.message import Message
    from dbus_next.service import ServiceInterface, dbus_property, method, signal as dbus_signal, PropertyAccess

    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False

    class Variant:  # type: ignore[no-redef]
        def __init__(self, signature: str, value: Any):
            self.signature = signature
            self.value = value


WATCHER_BUS_NAMES = ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher")
WATCHER_IFACES = ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher")
ITEM_IFACES = ("org.freedesktop.StatusNotifierItem", "org.kde.StatusNotifierItem")
DBUS_MENU_IFACE = "com.canonical.dbusmenu"
DEFAULT_ITEM_PATH = "/StatusNotifierItem"
WATCHER_PATH = "/StatusNotifierWatcher"
MENU_PROPS = [
    "type",
    "label",
    "enabled",
    "visible",
    "children-display",
    "toggle-type",
    "toggle-state",
    "icon-name",
    "icon-data",
]


def _variant_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _as_bool(value: Any, default: bool = False) -> bool:
    value = _variant_value(value)
    if value is None:
        return default
    return bool(value)


def _as_str(value: Any, default: str = "") -> str:
    value = _variant_value(value)
    if value is None:
        return default
    return str(value)


def _clean_menu_label(label: Any) -> str:
    """Remove DBusMenu mnemonic markers while preserving escaped underscores."""
    text = _as_str(label)
    if "_" not in text:
        return text
    marker = "\0UNDERSCORE\0"
    return text.replace("__", marker).replace("_", "").replace(marker, "_")


def _png_data_to_base64(data: Any) -> str:
    data = _variant_value(data)
    if not data:
        return ""
    try:
        if isinstance(data, str):
            return data
        if isinstance(data, bytearray):
            data = bytes(data)
        elif isinstance(data, list):
            data = bytes(int(b) & 0xFF for b in data)
        elif not isinstance(data, bytes):
            data = bytes(data)
        return base64.b64encode(data).decode()
    except Exception:
        return ""


def _is_object_path(value: str) -> bool:
    return value.startswith("/")


def _registered_id(service_name: str, object_path: str) -> str:
    if object_path == DEFAULT_ITEM_PATH:
        return service_name
    return f"{service_name}{object_path}"


def _argb_to_png_base64(width: int, height: int, data: bytes) -> str:
    """Convert SNI network-byte-order ARGB32 pixel data to a base64 PNG."""
    try:
        n_pixels = width * height
        raw = bytes(data)
        if width <= 0 or height <= 0 or len(raw) < n_pixels * 4:
            return ""

        bgra = bytearray(n_pixels * 4)
        for i in range(n_pixels):
            a = raw[i * 4]
            r = raw[i * 4 + 1]
            g = raw[i * 4 + 2]
            b = raw[i * 4 + 3]
            bgra[i * 4] = b
            bgra[i * 4 + 1] = g
            bgra[i * 4 + 2] = r
            bgra[i * 4 + 3] = a

        img = QImage(bytes(bgra), width, height, width * 4, QImage.Format.Format_ARGB32).copy()
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return base64.b64encode(buf.data().data()).decode()
    except Exception as e:
        log.debug("Failed to encode SNI pixmap: %s", e)
        return ""


def _pixmap_list_to_base64(pixmaps: Any) -> str:
    pixmaps = _variant_value(pixmaps) or []
    try:
        best = max(pixmaps, key=lambda p: int(p[0]) * int(p[1]))
        return _argb_to_png_base64(int(best[0]), int(best[1]), best[2])
    except Exception:
        return ""


def _icon_name_to_base64(icon_name: str, size: int = 24) -> str:
    try:
        if not icon_name:
            return ""
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


@dataclass
class TrayItem:
    id: str
    service_name: str
    object_path: str
    interface_name: str
    owner: str = ""
    title: str = ""
    status: str = "Active"
    category: str = "ApplicationStatus"
    icon_name: str = ""
    icon_pixmap: Any = field(default_factory=list)
    attention_icon_name: str = ""
    attention_icon_pixmap: Any = field(default_factory=list)
    tooltip_title: str = ""
    tooltip_text: str = ""
    menu_path: str = ""
    item_is_menu: bool = False

    def to_qml(self) -> dict[str, Any]:
        attention = self.status == "NeedsAttention"
        icon_name = self.attention_icon_name if attention and self.attention_icon_name else self.icon_name
        pixmaps = self.attention_icon_pixmap if attention and self.attention_icon_pixmap else self.icon_pixmap
        icon_b64 = _icon_name_to_base64(icon_name) or _pixmap_list_to_base64(pixmaps)
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "category": self.category,
            "tooltipTitle": self.tooltip_title,
            "tooltipText": self.tooltip_text,
            "iconName": icon_name,
            "iconBase64": icon_b64,
            "attention": attention,
            "itemIsMenu": self.item_is_menu,
            "hasMenu": bool(self.menu_path),
            "serviceName": self.service_name,
            "objectPath": self.object_path,
        }


class _WatcherInterface(ServiceInterface if HAS_DBUS else object):
    def __init__(self, service: "SystrayService", interface_name: str = "org.kde.StatusNotifierWatcher"):
        if HAS_DBUS:
            super().__init__(interface_name)
        self._svc = service

    if HAS_DBUS:

        @method()
        def RegisterStatusNotifierItem(self, service: "s"):
            self._svc._on_item_registered(service)

        @method()
        def RegisterStatusNotifierHost(self, service: "s"):
            self._svc._host_registered = True
            self.StatusNotifierHostRegistered()

        @dbus_property(access=PropertyAccess.READ)
        def RegisteredStatusNotifierItems(self) -> "as":
            return self._svc._registered_service_ids()

        @dbus_property(access=PropertyAccess.READ)
        def IsStatusNotifierHostRegistered(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def ProtocolVersion(self) -> "i":
            return 0

        @dbus_signal()
        def StatusNotifierItemRegistered(self, service: "s"):
            pass

        @dbus_signal()
        def StatusNotifierItemUnregistered(self, service: "s"):
            pass

        @dbus_signal()
        def StatusNotifierHostRegistered(self):
            pass


class DBusMenuClient:
    def __init__(self, service: "SystrayService"):
        self._svc = service

    async def fetch(self, item: TrayItem) -> list[dict[str, Any]]:
        if not item.menu_path:
            return []
        await self._call(item, "AboutToShow", "i", [0], ignore_errors=True)
        reply = await self._call(item, "GetLayout", "iias", [0, -1, MENU_PROPS])
        if not reply or not reply.body:
            return []
        body = [_variant_value(v) for v in reply.body]
        layout = body[-1]
        return self.normalize_layout(layout)

    async def trigger(self, item: TrayItem, menu_item_id: int):
        timestamp = int(time.time() * 1000) & 0xFFFFFFFF
        payload = Variant("s", "")
        await self._call(item, "Event", "isvu", [int(menu_item_id), "clicked", payload, timestamp], ignore_errors=True)

    async def _call(self, item: TrayItem, member: str, signature: str, body: list[Any], ignore_errors: bool = False):
        try:
            return await self._svc._bus.call(
                Message(
                    destination=item.service_name,
                    path=item.menu_path,
                    interface=DBUS_MENU_IFACE,
                    member=member,
                    signature=signature,
                    body=body,
                )
            )
        except Exception as e:
            if not ignore_errors:
                log.debug("DBusMenu %s failed for %s: %s", member, item.id, e)
            return None

    @staticmethod
    def normalize_layout(layout: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        def walk(node: Any, parent_id: int, depth: int):
            if hasattr(node, "value"):
                node = node.value
            if not isinstance(node, (list, tuple)) or len(node) < 2:
                return
            item_id = int(_variant_value(node[0]))
            props = _variant_value(node[1]) or {}
            children = _variant_value(node[2]) if len(node) > 2 else []
            if hasattr(children, "value"):
                children = children.value

            raw_label = _clean_menu_label(props.get("label"))
            icon_b64 = _png_data_to_base64(props.get("icon-data"))
            if not icon_b64:
                icon_b64 = _icon_name_to_base64(_as_str(props.get("icon-name")))
            image_preview = "<IMAGE>" in raw_label and bool(icon_b64)
            label = raw_label.replace("<IMAGE>", "").strip() if image_preview else raw_label

            normalized = {
                "id": item_id,
                "parentId": parent_id,
                "depth": depth,
                "type": _as_str(props.get("type"), "standard"),
                "label": label,
                "enabled": _as_bool(props.get("enabled"), True),
                "visible": _as_bool(props.get("visible"), True),
                "toggleType": _as_str(props.get("toggle-type")),
                "toggleState": int(_variant_value(props.get("toggle-state")) or 0),
                "iconName": _as_str(props.get("icon-name")),
                "iconBase64": icon_b64,
                "imagePreview": image_preview,
                "hasChildren": bool(children),
            }
            if item_id != 0:
                rows.append(normalized)
            child_parent_id = -1 if item_id == 0 else item_id
            for child in children or []:
                walk(child, child_parent_id, depth + 1)

        walk(layout, -1, -1)
        return [row for row in rows if row["visible"]]


class SystrayService(QObject):
    itemsChanged = Signal()
    menuItemsChanged = Signal()
    menuOpenForChanged = Signal()
    _itemsReady = Signal(list)
    _menuReady = Signal(str, list)

    def __init__(self, parent=None, start: bool = True):
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []
        self._menu_items: list[dict[str, Any]] = []
        self._menu_open_for = ""
        self._tray_items: dict[str, TrayItem] = {}
        self._owner_to_ids: dict[str, set[str]] = {}
        self._registered_args: dict[str, str] = {}
        self._host_registered = False
        self._owns_watcher = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus = None
        self._watcher_ifaces: list[_WatcherInterface] = []
        self._menu = DBusMenuClient(self)
        self._host_name = f"org.freedesktop.StatusNotifierHost-sadeshell-{os.getpid()}"

        self._itemsReady.connect(self._apply_items)
        self._menuReady.connect(self._apply_menu)

        if start and HAS_DBUS:
            self._start_loop()

    def _start_loop(self):
        def run():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._serve())
            except Exception as e:
                log.warning("SystrayService loop error: %s", e)

        threading.Thread(target=run, daemon=True, name="systray-dbus").start()

    async def _serve(self):
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._watcher_ifaces = [_WatcherInterface(self, watcher_iface) for watcher_iface in WATCHER_IFACES]
        for watcher_iface in self._watcher_ifaces:
            self._bus.export(WATCHER_PATH, watcher_iface)

        for watcher_name in WATCHER_BUS_NAMES:
            try:
                await self._bus.request_name(watcher_name)
                self._owns_watcher = True
                log.info("SystrayService: registered as %s", watcher_name)
            except DBusError:
                log.info("SystrayService: using existing %s", watcher_name)

        try:
            await self._bus.request_name(self._host_name)
        except DBusError as e:
            log.debug("Systray host name request failed: %s", e)

        self._bus.add_message_handler(self._handle_message)
        await self._add_match("type='signal',interface='org.kde.StatusNotifierWatcher'")
        await self._add_match("type='signal',interface='org.freedesktop.StatusNotifierWatcher'")
        await self._add_match("type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged'")

        for watcher_name in WATCHER_BUS_NAMES:
            for watcher_iface in WATCHER_IFACES:
                await self._call_watcher(
                    "RegisterStatusNotifierHost",
                    "s",
                    [self._host_name],
                    watcher_iface,
                    watcher_name,
                )

        await self._fetch_existing_items()
        await self._bus.wait_for_disconnect()

    async def _add_match(self, rule: str):
        await self._bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[rule],
            )
        )

    async def _fetch_existing_items(self):
        seen: set[str] = set()
        for watcher_name in WATCHER_BUS_NAMES:
            for watcher_iface in WATCHER_IFACES:
                try:
                    reply = await self._bus.call(
                        Message(
                            destination=watcher_name,
                            path=WATCHER_PATH,
                            interface="org.freedesktop.DBus.Properties",
                            member="Get",
                            signature="ss",
                            body=[watcher_iface, "RegisteredStatusNotifierItems"],
                        )
                    )
                    if not reply or not reply.body:
                        continue
                    for service_id in _variant_value(reply.body[0]) or []:
                        if service_id in seen:
                            continue
                        seen.add(service_id)
                        asyncio.ensure_future(self._register_item(service_id))
                except Exception:
                    pass

    async def _call_watcher(
        self,
        member: str,
        signature: str,
        body: list[Any],
        iface: str,
        destination: str = "org.kde.StatusNotifierWatcher",
    ):
        try:
            return await self._bus.call(
                Message(
                    destination=destination,
                    path=WATCHER_PATH,
                    interface=iface,
                    member=member,
                    signature=signature,
                    body=body,
                )
            )
        except Exception as e:
            log.debug("Watcher call %s/%s on %s failed: %s", iface, member, destination, e)
            return None

    def _handle_message(self, message) -> bool:
        if not hasattr(message, "interface"):
            return False

        if message.message_type == getattr(MessageType, "METHOD_CALL", None):
            return self._handle_method_call(message)

        if message.message_type != MessageType.SIGNAL:
            return False

        iface = message.interface or ""
        member = message.member or ""

        if iface in WATCHER_IFACES:
            if member == "StatusNotifierItemRegistered" and message.body:
                asyncio.ensure_future(self._register_item(message.body[0], getattr(message, "sender", "") or ""))
            elif member == "StatusNotifierItemUnregistered" and message.body:
                self._remove_item_by_registered_arg(message.body[0])
        elif iface == "org.freedesktop.DBus" and member == "NameOwnerChanged" and len(message.body) >= 3:
            name, old_owner, new_owner = message.body[:3]
            if new_owner == "" and old_owner != "":
                self._remove_items_by_owner(old_owner)
                self._remove_items_by_owner(name)
        elif iface in ITEM_IFACES and member in {
            "NewIcon",
            "NewAttentionIcon",
            "NewOverlayIcon",
            "NewTitle",
            "NewStatus",
            "NewToolTip",
        }:
            for item_id in self._ids_for_sender(getattr(message, "sender", "") or "", getattr(message, "path", "") or ""):
                asyncio.ensure_future(self._refresh_item(item_id))
        elif iface == DBUS_MENU_IFACE and member in {"LayoutUpdated", "ItemsPropertiesUpdated"}:
            if self._menu_open_for:
                asyncio.ensure_future(self._open_menu(self._menu_open_for))
        return False

    def _handle_method_call(self, message) -> bool:
        if message.path != WATCHER_PATH or message.interface not in WATCHER_IFACES:
            return False

        if message.member == "RegisterStatusNotifierItem" and message.body:
            self._on_item_registered(message.body[0], getattr(message, "sender", "") or "")
            if self._bus:
                self._bus.send(Message.new_method_return(message))
            return True

        if message.member == "RegisterStatusNotifierHost":
            self._host_registered = True
            for watcher_iface in self._watcher_ifaces:
                watcher_iface.StatusNotifierHostRegistered()
            if self._bus:
                self._bus.send(Message.new_method_return(message))
            return True

        return False

    def _on_item_registered(self, service: str, sender: str = ""):
        asyncio.ensure_future(self._register_item(service, sender))

    def _registered_service_ids(self) -> list[str]:
        return list(self._registered_args.values())

    def _resolve_registration(self, service_id: str, sender: str = "") -> tuple[str, str, str]:
        if _is_object_path(service_id):
            service_name = sender
            object_path = service_id
        elif "/" in service_id:
            service_name, object_path = service_id.split("/", 1)
            object_path = "/" + object_path
        else:
            service_name = service_id
            object_path = DEFAULT_ITEM_PATH
        item_id = _registered_id(service_name, object_path)
        return service_name, object_path, item_id

    async def _get_name_owner(self, service_name: str) -> str:
        if service_name.startswith(":"):
            return service_name
        try:
            reply = await self._bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="GetNameOwner",
                    signature="s",
                    body=[service_name],
                )
            )
            if reply and reply.body:
                return str(reply.body[0])
        except Exception:
            pass
        return service_name

    async def _get_property(self, service_name: str, object_path: str, prop: str, default: Any = None):
        for iface in ITEM_IFACES:
            try:
                reply = await self._bus.call(
                    Message(
                        destination=service_name,
                        path=object_path,
                        interface="org.freedesktop.DBus.Properties",
                        member="Get",
                        signature="ss",
                        body=[iface, prop],
                    )
                )
                if reply and reply.message_type == MessageType.METHOD_RETURN and reply.body:
                    return _variant_value(reply.body[0]), iface
            except Exception:
                pass
        return default, ""

    async def _register_item(self, service_id: str, sender: str = ""):
        service_name, object_path, item_id = self._resolve_registration(service_id, sender)
        if not service_name:
            log.debug("Ignoring SNI registration without a service owner: %s", service_id)
            return

        owner = await self._get_name_owner(service_name)
        try:
            title, iface = await self._get_property(service_name, object_path, "Title", "")
            if not iface:
                iface = ITEM_IFACES[0]
            status, _ = await self._get_property(service_name, object_path, "Status", "Active")
            category, _ = await self._get_property(service_name, object_path, "Category", "ApplicationStatus")
            icon_name, _ = await self._get_property(service_name, object_path, "IconName", "")
            icon_pixmap, _ = await self._get_property(service_name, object_path, "IconPixmap", [])
            attention_icon_name, _ = await self._get_property(service_name, object_path, "AttentionIconName", "")
            attention_icon_pixmap, _ = await self._get_property(service_name, object_path, "AttentionIconPixmap", [])
            tooltip, _ = await self._get_property(service_name, object_path, "ToolTip", None)
            menu_path, _ = await self._get_property(service_name, object_path, "Menu", "")
            item_is_menu, _ = await self._get_property(service_name, object_path, "ItemIsMenu", False)

            tooltip_title = ""
            tooltip_text = ""
            tooltip = _variant_value(tooltip)
            if isinstance(tooltip, (list, tuple)) and len(tooltip) >= 4:
                tooltip_title = _as_str(tooltip[2])
                tooltip_text = _as_str(tooltip[3])

            item = TrayItem(
                id=item_id,
                service_name=service_name,
                object_path=object_path,
                interface_name=iface,
                owner=owner,
                title=_as_str(title),
                status=_as_str(status, "Active"),
                category=_as_str(category, "ApplicationStatus"),
                icon_name=_as_str(icon_name),
                icon_pixmap=_variant_value(icon_pixmap) or [],
                attention_icon_name=_as_str(attention_icon_name),
                attention_icon_pixmap=_variant_value(attention_icon_pixmap) or [],
                tooltip_title=tooltip_title,
                tooltip_text=tooltip_text,
                menu_path=_as_str(menu_path),
                item_is_menu=_as_bool(item_is_menu),
            )
            is_new = item_id not in self._tray_items
            for ids in self._owner_to_ids.values():
                ids.discard(item_id)
            self._tray_items[item_id] = item
            self._registered_args[item_id] = service_id
            self._owner_to_ids.setdefault(owner, set()).add(item_id)
            self._owner_to_ids.setdefault(service_name, set()).add(item_id)
            self._publish_items()

            for iface_name in ITEM_IFACES:
                await self._add_match(
                    f"type='signal',sender='{owner}',path='{object_path}',interface='{iface_name}'"
                )
            if item.menu_path:
                await self._add_match(
                    f"type='signal',sender='{owner}',path='{item.menu_path}',interface='{DBUS_MENU_IFACE}'"
                )
            if is_new and self._owns_watcher:
                for watcher_iface in self._watcher_ifaces:
                    watcher_iface.StatusNotifierItemRegistered(service_id)
        except Exception as e:
            log.debug("Failed to register SNI item %s: %s", service_id, e)

    async def _refresh_item(self, item_id: str):
        if item_id not in self._tray_items:
            return
        await self._register_item(self._registered_args.get(item_id, item_id), self._tray_items[item_id].service_name)

    def _ids_for_sender(self, sender: str, path: str) -> list[str]:
        ids = self._owner_to_ids.get(sender, set()) | self._owner_to_ids.get(sender or "", set())
        if not path:
            return list(ids)
        return [item_id for item_id in ids if self._tray_items.get(item_id) and self._tray_items[item_id].object_path == path]

    def _remove_item_by_registered_arg(self, service_id: str):
        for item_id, registered in list(self._registered_args.items()):
            if registered == service_id or item_id == service_id:
                self._remove_item(item_id)

    def _remove_items_by_owner(self, owner: str):
        for item_id in list(self._owner_to_ids.get(owner, set())):
            self._remove_item(item_id)

    def _remove_item(self, item_id: str):
        item = self._tray_items.pop(item_id, None)
        registered_arg = self._registered_args.pop(item_id, item_id)
        if item:
            for ids in self._owner_to_ids.values():
                ids.discard(item_id)
            if self._menu_open_for == item_id:
                self._menuReady.emit("", [])
            if self._owns_watcher:
                for watcher_iface in self._watcher_ifaces:
                    watcher_iface.StatusNotifierItemUnregistered(registered_arg)
            self._publish_items()

    def _publish_items(self):
        visible = [
            item.to_qml()
            for item in self._tray_items.values()
            if item.status != "Passive"
        ]
        self._itemsReady.emit(visible)

    def _apply_items(self, items: list[dict[str, Any]]):
        self._items = items
        self.itemsChanged.emit()

    def _apply_menu(self, item_id: str, menu_items: list[dict[str, Any]]):
        self._menu_open_for = item_id
        self._menu_items = menu_items
        self.menuOpenForChanged.emit()
        self.menuItemsChanged.emit()

    @Property("QVariantList", notify=itemsChanged)
    def items(self):
        return self._items

    @Property("QVariantList", notify=menuItemsChanged)
    def menuItems(self):
        return self._menu_items

    @Property(str, notify=menuOpenForChanged)
    def menuOpenFor(self):
        return self._menu_open_for

    async def _call_item_method(self, item_id: str, member: str, signature: str, body: list[Any]):
        item = self._tray_items.get(item_id)
        if not item:
            return
        for iface in (item.interface_name, *ITEM_IFACES):
            if not iface:
                continue
            try:
                await self._bus.call(
                    Message(
                        destination=item.service_name,
                        path=item.object_path,
                        interface=iface,
                        member=member,
                        signature=signature,
                        body=body,
                    )
                )
                return
            except Exception:
                continue
        log.debug("SNI method %s failed for %s", member, item_id)

    def _schedule(self, coro):
        if self._loop:
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    @Slot(str, int, int)
    def activate(self, item_id: str, x: int, y: int):
        item = self._tray_items.get(item_id)
        if item and item.item_is_menu and item.menu_path:
            self.openMenu(item_id, x, y)
            return
        self._schedule(self._call_item_method(item_id, "Activate", "ii", [x, y]))

    @Slot(str, int, int)
    def secondaryActivate(self, item_id: str, x: int, y: int):
        self._schedule(self._call_item_method(item_id, "SecondaryActivate", "ii", [x, y]))

    @Slot(str, int, str)
    def scroll(self, item_id: str, delta: int, orientation: str):
        self._schedule(self._call_item_method(item_id, "Scroll", "is", [delta, orientation]))

    @Slot(str, int, int)
    def openMenu(self, item_id: str, x: int = 0, y: int = 0):
        self._schedule(self._open_menu(item_id, x, y))

    async def _open_menu(self, item_id: str, x: int = 0, y: int = 0):
        item = self._tray_items.get(item_id)
        if not item:
            return
        if not item.menu_path:
            await self._call_item_method(item_id, "ContextMenu", "ii", [x, y])
            return
        menu_items = await self._menu.fetch(item)
        self._menuReady.emit(item_id, menu_items)

    @Slot(str, int)
    def triggerMenuItem(self, item_id: str, menu_item_id: int):
        async def run():
            item = self._tray_items.get(item_id)
            if item:
                await self._menu.trigger(item, menu_item_id)
            self._menuReady.emit("", [])

        self._schedule(run())

    @Slot()
    def closeMenu(self):
        self._menu_open_for = ""
        self._menu_items = []
        self.menuOpenForChanged.emit()
        self.menuItemsChanged.emit()
