import asyncio
import os
import sys
import types
import unittest
from unittest import mock


if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtgui = types.ModuleType("PySide6.QtGui")

    class _Signal:
        def __init__(self, *args):
            self._handlers = []

        def connect(self, handler):
            self._handlers.append(handler)

        def emit(self, *args):
            for handler in list(self._handlers):
                handler(*args)

    class _QObject:
        def __init__(self, parent=None):
            pass

    def _Property(*args, **kwargs):
        def decorator(fn):
            return property(fn)
        return decorator

    def _Slot(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    class _QBuffer:
        def open(self, mode):
            pass

        def data(self):
            return types.SimpleNamespace(data=lambda: b"png")

    class _OpenModeFlag:
        WriteOnly = 1

    class _QIODeviceBase:
        OpenModeFlag = _OpenModeFlag

    class _QIcon:
        @staticmethod
        def fromTheme(name):
            return _QIcon()

        def isNull(self):
            return True

    class _QImage:
        class Format:
            Format_ARGB32 = 0

        def __init__(self, *args):
            pass

        def copy(self):
            return self

        def save(self, *args):
            return True

    qtcore.QObject = _QObject
    qtcore.Property = _Property
    qtcore.Signal = _Signal
    qtcore.Slot = _Slot
    qtcore.QBuffer = _QBuffer
    qtcore.QIODeviceBase = _QIODeviceBase
    qtgui.QIcon = _QIcon
    qtgui.QImage = _QImage
    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
else:
    pyside6 = sys.modules["PySide6"]
    qtcore = sys.modules.get("PySide6.QtCore", types.ModuleType("PySide6.QtCore"))
    qtgui = sys.modules.get("PySide6.QtGui", types.ModuleType("PySide6.QtGui"))
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui

    class _Signal:
        def __init__(self, *args):
            self._handlers = []

        def connect(self, handler):
            self._handlers.append(handler)

        def emit(self, *args):
            for handler in list(self._handlers):
                handler(*args)

    class _QObject:
        def __init__(self, parent=None):
            pass

    def _Property(*args, **kwargs):
        def decorator(fn):
            return property(fn)
        return decorator

    def _Slot(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    class _QBuffer:
        def open(self, mode):
            pass

        def data(self):
            return types.SimpleNamespace(data=lambda: b"png")

    class _OpenModeFlag:
        WriteOnly = 1

    class _QIODeviceBase:
        OpenModeFlag = _OpenModeFlag

    class _QIcon:
        @staticmethod
        def fromTheme(name):
            return _QIcon()

        def isNull(self):
            return True

    class _QImage:
        class Format:
            Format_ARGB32 = 0

        def __init__(self, *args):
            pass

        def copy(self):
            return self

        def save(self, *args):
            return True

    qtcore.QObject = getattr(qtcore, "QObject", _QObject)
    qtcore.Property = getattr(qtcore, "Property", _Property)
    qtcore.Signal = getattr(qtcore, "Signal", _Signal)
    qtcore.Slot = getattr(qtcore, "Slot", _Slot)
    qtcore.QBuffer = getattr(qtcore, "QBuffer", _QBuffer)
    qtcore.QIODeviceBase = getattr(qtcore, "QIODeviceBase", _QIODeviceBase)
    qtgui.QIcon = getattr(qtgui, "QIcon", _QIcon)
    qtgui.QImage = getattr(qtgui, "QImage", _QImage)


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.bar import systray_service  # noqa: E402


class _MessageType:
    METHOD_CALL = 1
    METHOD_RETURN = 2
    SIGNAL = 4


class _Message:
    def __init__(
        self,
        destination=None,
        path=None,
        interface=None,
        member=None,
        signature="",
        body=None,
        message_type=None,
        sender="",
    ):
        self.destination = destination
        self.path = path
        self.interface = interface
        self.member = member
        self.signature = signature
        self.body = body or []
        self.message_type = message_type
        self.sender = sender

    @staticmethod
    def new_method_return(message, signature="", body=None, unix_fds=None):
        del message, signature, unix_fds
        return _Message(message_type=_MessageType.METHOD_RETURN, body=body or [])


class _Reply:
    def __init__(self, body=None):
        self.message_type = _MessageType.METHOD_RETURN
        self.body = body or []


class _Variant:
    def __init__(self, signature, value):
        self.signature = signature
        self.value = value


class _FakeBus:
    def __init__(self):
        self.calls = []
        self.sent = []
        self.properties = {}
        self.owners = {}
        self.fail_methods = set()
        self.menu_layout = None
        self.watcher_items = {
            ("org.kde.StatusNotifierWatcher", "org.kde.StatusNotifierWatcher"): ["org.startup.App"]
        }

    def set_prop(self, service, path, iface, prop, value):
        self.properties[(service, path, iface, prop)] = value

    async def call(self, message):
        self.calls.append(message)
        if message.destination == "org.freedesktop.DBus" and message.member == "GetNameOwner":
            return _Reply([self.owners.get(message.body[0], message.body[0])])
        if message.destination == "org.freedesktop.DBus" and message.member == "AddMatch":
            return _Reply([])
        if (
            message.destination in systray_service.WATCHER_BUS_NAMES
            and message.interface == "org.freedesktop.DBus.Properties"
            and message.member == "Get"
        ):
            return _Reply([_Variant("as", self.watcher_items.get((message.destination, message.body[0]), []))])
        if message.interface == "org.freedesktop.DBus.Properties" and message.member == "Get":
            iface, prop = message.body
            key = (message.destination, message.path, iface, prop)
            if key not in self.properties:
                raise RuntimeError(f"missing property {key}")
            return _Reply([_Variant("", self.properties[key])])
        if message.interface == systray_service.DBUS_MENU_IFACE:
            if message.member == "GetLayout":
                return _Reply([1, self.menu_layout])
            return _Reply([])
        if (message.interface, message.member) in self.fail_methods:
            raise RuntimeError("method failed")
        return _Reply([])

    def send(self, message):
        self.sent.append(message)


def _make_service(bus=None):
    systray_service.Message = _Message
    systray_service.MessageType = _MessageType
    systray_service.Variant = _Variant
    svc = systray_service.SystrayService(start=False)
    svc._bus = bus or _FakeBus()
    return svc


class TestSystrayService(unittest.IsolatedAsyncioTestCase):
    async def test_bus_name_registration_resolves_default_path(self):
        bus = _FakeBus()
        bus.owners["org.app.Tray"] = ":1.20"
        bus.set_prop("org.app.Tray", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Tray")
        svc = _make_service(bus)

        await svc._register_item("org.app.Tray")

        self.assertIn("org.app.Tray", svc._tray_items)
        item = svc._tray_items["org.app.Tray"]
        self.assertEqual(item.object_path, "/StatusNotifierItem")
        self.assertEqual(item.owner, ":1.20")
        self.assertEqual(svc.items[0]["title"], "Tray")

    async def test_path_only_registration_uses_sender(self):
        bus = _FakeBus()
        bus.set_prop(":1.44", "/CustomTray", "org.freedesktop.StatusNotifierItem", "Title", "Qt App")
        svc = _make_service(bus)

        await svc._register_item("/CustomTray", sender=":1.44")

        self.assertIn(":1.44/CustomTray", svc._tray_items)
        item = svc._tray_items[":1.44/CustomTray"]
        self.assertEqual(item.service_name, ":1.44")
        self.assertEqual(item.object_path, "/CustomTray")

    async def test_low_level_watcher_registration_keeps_method_sender(self):
        bus = _FakeBus()
        bus.set_prop(":1.55", "/QtTray", "org.freedesktop.StatusNotifierItem", "Title", "Qt Low")
        svc = _make_service(bus)

        handled = svc._handle_message(
            _Message(
                path=systray_service.WATCHER_PATH,
                interface="org.kde.StatusNotifierWatcher",
                member="RegisterStatusNotifierItem",
                body=["/QtTray"],
                message_type=_MessageType.METHOD_CALL,
                sender=":1.55",
            )
        )
        await asyncio.sleep(0.01)

        self.assertTrue(handled)
        self.assertIn(":1.55/QtTray", svc._tray_items)
        self.assertEqual(svc.items[0]["title"], "Qt Low")
        self.assertEqual(len(bus.sent), 1)

    async def test_kde_interface_properties_are_supported(self):
        bus = _FakeBus()
        bus.set_prop("org.kde.App", "/StatusNotifierItem", "org.kde.StatusNotifierItem", "Title", "KDE")
        bus.set_prop("org.kde.App", "/StatusNotifierItem", "org.kde.StatusNotifierItem", "Status", "NeedsAttention")
        svc = _make_service(bus)

        await svc._register_item("org.kde.App")

        item = svc._tray_items["org.kde.App"]
        self.assertEqual(item.interface_name, "org.kde.StatusNotifierItem")
        self.assertTrue(svc.items[0]["attention"])

    async def test_passive_items_are_published_dimmed(self):
        bus = _FakeBus()
        bus.set_prop("org.hidden.App", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Hidden")
        bus.set_prop("org.hidden.App", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Status", "Passive")
        svc = _make_service(bus)

        await svc._register_item("org.hidden.App")

        self.assertIn("org.hidden.App", svc._tray_items)
        self.assertEqual(svc.items[0]["title"], "Hidden")
        self.assertEqual(svc.items[0]["source"], "sni")
        self.assertTrue(svc.items[0]["passive"])

    async def test_owner_loss_removes_matching_item(self):
        bus = _FakeBus()
        bus.owners["org.app.One"] = ":1.1"
        bus.owners["org.app.Two"] = ":1.2"
        bus.set_prop("org.app.One", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "One")
        bus.set_prop("org.app.Two", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Two")
        svc = _make_service(bus)

        await svc._register_item("org.app.One")
        await svc._register_item("org.app.Two")
        svc._remove_items_by_owner(":1.1")

        self.assertNotIn("org.app.One", svc._tray_items)
        self.assertIn("org.app.Two", svc._tray_items)
        self.assertEqual([item["title"] for item in svc.items], ["Two"])

    async def test_owner_loss_closes_open_menu_for_removed_item(self):
        bus = _FakeBus()
        bus.owners["org.app.One"] = ":1.1"
        bus.set_prop("org.app.One", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "One")
        svc = _make_service(bus)
        await svc._register_item("org.app.One")
        svc._menu_open_for = "org.app.One"
        svc._menu_items = [{"id": 1}]

        svc._handle_message(
            _Message(
                interface="org.freedesktop.DBus",
                member="NameOwnerChanged",
                message_type=_MessageType.SIGNAL,
                body=["org.app.One", ":1.1", ""],
            )
        )

        self.assertNotIn("org.app.One", svc._tray_items)
        self.assertEqual(svc.menuOpenFor, "")
        self.assertEqual(svc.menuItems, [])

    async def test_unregister_signal_removes_item_and_closes_open_menu(self):
        bus = _FakeBus()
        bus.set_prop("org.app.One", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "One")
        svc = _make_service(bus)
        await svc._register_item("org.app.One")
        svc._menu_open_for = "org.app.One"
        svc._menu_items = [{"id": 1}]

        svc._handle_message(
            _Message(
                interface="org.kde.StatusNotifierWatcher",
                member="StatusNotifierItemUnregistered",
                message_type=_MessageType.SIGNAL,
                body=["org.app.One"],
            )
        )

        self.assertNotIn("org.app.One", svc._tray_items)
        self.assertEqual(svc.menuOpenFor, "")
        self.assertEqual(svc.menuItems, [])

    async def test_existing_watcher_items_are_loaded(self):
        bus = _FakeBus()
        bus.set_prop("org.startup.App", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Startup")
        svc = _make_service(bus)

        await svc._fetch_existing_items()
        await asyncio.sleep(0.01)

        self.assertIn("org.startup.App", svc._tray_items)
        self.assertEqual(svc.items[0]["title"], "Startup")

    async def test_existing_items_are_loaded_from_freedesktop_watcher_name(self):
        bus = _FakeBus()
        bus.watcher_items = {
            ("org.kde.StatusNotifierWatcher", "org.kde.StatusNotifierWatcher"): [],
            ("org.freedesktop.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher"): ["org.compat.App"],
        }
        bus.set_prop("org.compat.App", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Compat")
        svc = _make_service(bus)

        await svc._fetch_existing_items()
        await asyncio.sleep(0.01)

        self.assertIn("org.compat.App", svc._tray_items)
        self.assertEqual(svc.items[0]["title"], "Compat")

    async def test_registers_host_with_requested_watcher_destination(self):
        bus = _FakeBus()
        svc = _make_service(bus)

        await svc._call_watcher(
            "RegisterStatusNotifierHost",
            "s",
            ["org.freedesktop.StatusNotifierHost-test"],
            "org.freedesktop.StatusNotifierWatcher",
            "org.freedesktop.StatusNotifierWatcher",
        )

        self.assertEqual(bus.calls[-1].destination, "org.freedesktop.StatusNotifierWatcher")
        self.assertEqual(bus.calls[-1].interface, "org.freedesktop.StatusNotifierWatcher")

    async def test_update_signal_refreshes_item(self):
        bus = _FakeBus()
        bus.owners["org.app.Refresh"] = ":1.9"
        bus.set_prop("org.app.Refresh", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "Old")
        svc = _make_service(bus)
        await svc._register_item("org.app.Refresh")
        bus.set_prop("org.app.Refresh", "/StatusNotifierItem", "org.freedesktop.StatusNotifierItem", "Title", "New")

        svc._handle_message(
            _Message(
                interface="org.freedesktop.StatusNotifierItem",
                member="NewTitle",
                message_type=_MessageType.SIGNAL,
                sender=":1.9",
                path="/StatusNotifierItem",
            )
        )
        await asyncio.sleep(0)

        self.assertEqual(svc.items[0]["title"], "New")

    async def test_method_calls_fall_back_across_interfaces(self):
        bus = _FakeBus()
        bus.fail_methods.add(("org.freedesktop.StatusNotifierItem", "Activate"))
        svc = _make_service(bus)
        svc._tray_items["app"] = systray_service.TrayItem(
            id="app",
            service_name="org.app",
            object_path="/StatusNotifierItem",
            interface_name="org.freedesktop.StatusNotifierItem",
        )

        await svc._call_item_method("app", "Activate", "ii", [10, 20])

        methods = [(call.interface, call.member) for call in bus.calls]
        self.assertIn(("org.freedesktop.StatusNotifierItem", "Activate"), methods)
        self.assertIn(("org.kde.StatusNotifierItem", "Activate"), methods)

    async def test_secondary_and_scroll_actions_dispatch(self):
        bus = _FakeBus()
        svc = _make_service(bus)
        svc._tray_items["app"] = systray_service.TrayItem(
            id="app",
            service_name="org.app",
            object_path="/StatusNotifierItem",
            interface_name="org.freedesktop.StatusNotifierItem",
        )

        await svc._call_item_method("app", "SecondaryActivate", "ii", [1, 2])
        await svc._call_item_method("app", "Scroll", "is", [120, "vertical"])

        sent = [(call.member, call.signature, call.body) for call in bus.calls]
        self.assertIn(("SecondaryActivate", "ii", [1, 2]), sent)
        self.assertIn(("Scroll", "is", [120, "vertical"]), sent)

    async def test_dbusmenu_layout_is_normalized_and_triggered(self):
        bus = _FakeBus()
        bus.menu_layout = (
            0,
            {},
            [
                (1, {"label": _Variant("s", "Open"), "enabled": _Variant("b", True)}, []),
                (2, {"label": _Variant("s", "1. <IMAGE>"), "icon-data": _Variant("ay", b"\x89PNG\r\n")}, []),
                (5, {"type": _Variant("s", "separator")}, []),
                (
                    3,
                    {"label": _Variant("s", "_More"), "children-display": _Variant("s", "submenu")},
                    [(4, {"label": _Variant("s", "Nested __Label"), "toggle-type": _Variant("s", "checkmark"), "toggle-state": _Variant("i", 1)}, [])],
                ),
            ],
        )
        svc = _make_service(bus)
        item = systray_service.TrayItem(
            id="app",
            service_name="org.app",
            object_path="/StatusNotifierItem",
            interface_name="org.freedesktop.StatusNotifierItem",
            menu_path="/Menu",
        )
        svc._tray_items["app"] = item

        await svc._open_menu("app")
        await svc._menu.trigger(item, 4)

        self.assertEqual([row["id"] for row in svc.menuItems], [1, 2, 5, 3, 4])
        self.assertEqual(svc.menuItems[0]["parentId"], -1)
        self.assertEqual(svc.menuItems[1]["parentId"], -1)
        self.assertEqual(svc.menuItems[3]["parentId"], -1)
        self.assertEqual(svc.menuItems[1]["label"], "1.")
        self.assertTrue(svc.menuItems[1]["imagePreview"])
        self.assertTrue(svc.menuItems[1]["iconBase64"])
        self.assertEqual(svc.menuItems[3]["label"], "More")
        self.assertEqual(svc.menuItems[4]["label"], "Nested _Label")
        self.assertTrue(svc.menuItems[3]["hasChildren"])
        self.assertEqual(svc.menuItems[4]["parentId"], 3)
        self.assertTrue(any(call.member == "AboutToShow" for call in bus.calls))
        self.assertTrue(any(call.member == "GetLayout" for call in bus.calls))
        event_calls = [call for call in bus.calls if call.member == "Event"]
        self.assertEqual(event_calls[-1].body[0], 4)

    def test_icon_selection_prefers_attention_pixmap_for_needs_attention(self):
        with mock.patch.object(systray_service, "_icon_name_to_base64", return_value=""), mock.patch.object(
            systray_service, "_pixmap_list_to_base64", side_effect=lambda pixmaps: pixmaps[0][2].decode()
        ):
            item = systray_service.TrayItem(
                id="app",
                service_name="org.app",
                object_path="/StatusNotifierItem",
                interface_name="org.freedesktop.StatusNotifierItem",
                status="NeedsAttention",
                icon_pixmap=[(1, 1, b"normal")],
                attention_icon_pixmap=[(1, 1, b"attention")],
            )

            self.assertEqual(item.to_qml()["iconBase64"], "attention")

    def test_xembed_item_is_published_and_removed(self):
        svc = _make_service()
        item = systray_service.XEmbedTrayItem(id="xembed:42", window_id=42, container_id=420)

        svc._add_xembed_item(item.to_qml())

        self.assertEqual(svc.items[0]["source"], "xembed")
        self.assertEqual(svc.items[0]["xWindowId"], 42)

        svc._remove_xembed_item("xembed:42")

        self.assertEqual(svc.items, [])

    def test_xembed_geometry_is_forwarded_to_host(self):
        svc = _make_service()
        host = mock.Mock()
        svc._xembed_host = host

        svc.setXEmbedGeometry("xembed:42", 1, 2, 24, 24)
        svc.setXEmbedVisible(False)

        host.set_geometry.assert_called_once_with("xembed:42", 1, 2, 24, 24)
        host.set_visible.assert_called_once_with(False)

    def test_xembed_host_duplicate_dock_is_ignored(self):
        svc = _make_service()
        host = systray_service.XEmbedTrayHost(svc)
        host._items[42] = systray_service.XEmbedTrayItem(id="xembed:42", window_id=42, container_id=420)

        host._dock_window(42)

        self.assertEqual(list(host._items), [42])

    def test_xembed_host_remove_window_emits_removal(self):
        class _FakeWindow:
            def unmap(self):
                pass

            def reparent(self, *args):
                pass

            def destroy(self):
                pass

        class _FakeDisplay:
            def create_resource_object(self, *args):
                return _FakeWindow()

            def flush(self):
                pass

        svc = _make_service()
        host = systray_service.XEmbedTrayHost(svc)
        host._display = _FakeDisplay()
        host._root = object()
        item = systray_service.XEmbedTrayItem(id="xembed:42", window_id=42, container_id=420)
        host._items[42] = item
        host._geometries[item.id] = (1, 2, 24, 24)
        svc._add_xembed_item(item.to_qml())

        host._remove_window(42)

        self.assertNotIn(42, host._items)
        self.assertNotIn(item.id, host._geometries)
        self.assertEqual(svc.items, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
