"""NotificationService — D-Bus notification server."""

import threading
import asyncio

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, signal as dbus_signal
    from dbus_next import Variant, BusType
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class NotificationService(QObject):
    notificationsChanged = Signal()
    popupQueueChanged = Signal()
    unreadCountChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications = []
        self._popup_queue = []
        self._next_id = 1

        if HAS_DBUS:
            self._start_server()

    def _start_server(self):
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._serve(loop))
            except Exception:
                pass
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    async def _serve(self, loop):
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        iface = NotificationDBusInterface(self)
        bus.export("/org/freedesktop/Notifications", iface)
        await bus.request_name("org.freedesktop.Notifications")
        await bus.wait_for_disconnect()

    def _add_notification(self, app_name, summary, body, app_icon, expire_timeout):
        notif_id = self._next_id
        self._next_id += 1

        entry = {
            "id": notif_id,
            "summary": summary or "",
            "body": body or "",
            "appName": app_name or "",
            "appIcon": app_icon or "",
            "image": "",
            "expireTimeout": expire_timeout if expire_timeout > 0 else 5000,
        }

        self._notifications.insert(0, entry)
        self._popup_queue.insert(0, entry)
        self.notificationsChanged.emit()
        self.popupQueueChanged.emit()
        self.unreadCountChanged.emit()
        return notif_id

    @Property("QVariantList", notify=notificationsChanged)
    def notifications(self):
        return self._notifications

    @Property("QVariantList", notify=popupQueueChanged)
    def popupQueue(self):
        return self._popup_queue

    @Property(int, notify=unreadCountChanged)
    def unreadCount(self):
        return len(self._notifications)

    @Slot(int)
    def dismiss(self, index):
        if 0 <= index < len(self._notifications):
            self._notifications.pop(index)
            self.notificationsChanged.emit()
            self.unreadCountChanged.emit()

    @Slot()
    def dismissAll(self):
        self._notifications.clear()
        self._popup_queue.clear()
        self.notificationsChanged.emit()
        self.popupQueueChanged.emit()
        self.unreadCountChanged.emit()

    @Slot("QVariant")
    def removeFromQueue(self, entry):
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        if entry_id is not None:
            self._popup_queue = [e for e in self._popup_queue if e.get("id") != entry_id]
            self.popupQueueChanged.emit()


if HAS_DBUS:
    class NotificationDBusInterface(ServiceInterface):
        def __init__(self, service):
            super().__init__("org.freedesktop.Notifications")
            self._service = service

        @method()
        def GetCapabilities(self) -> 'as':
            return ["body", "body-markup", "actions", "persistence", "icon-static"]

        @method()
        def GetServerInformation(self) -> 'ssss':
            return ["sadeshell", "sadeshell", "0.1", "1.2"]

        @method()
        def Notify(self, app_name: 's', replaces_id: 'u', app_icon: 's',
                   summary: 's', body: 's', actions: 'as',
                   hints: 'a{sv}', expire_timeout: 'i') -> 'u':
            notif_id = self._service._add_notification(
                app_name, summary, body, app_icon, expire_timeout
            )
            return notif_id

        @method()
        def CloseNotification(self, id: 'u'):
            pass
