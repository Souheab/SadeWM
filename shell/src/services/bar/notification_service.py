"""NotificationService — D-Bus notification server."""

import asyncio
import threading

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, signal as dbus_signal
    from dbus_next import Variant, BusType
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class PopupQueueModel(QAbstractListModel):
    """Row-aware popup model so each toast keeps its own lifecycle."""

    NotificationRole = int(Qt.ItemDataRole.UserRole) + 1
    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []

    def roleNames(self):
        return {self.NotificationRole: b"notification"}

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        if role == self.NotificationRole:
            return self._entries[index.row()]
        return None

    @property
    def entries(self):
        return self._entries

    def prepend(self, entry):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._entries.insert(0, entry)
        self.endInsertRows()
        self.countChanged.emit()

    def remove_by_id(self, notification_id):
        row = next(
            (i for i, entry in enumerate(self._entries)
             if entry.get("id") == notification_id),
            -1,
        )
        if row < 0:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._entries.pop(row)
        self.endRemoveRows()
        self.countChanged.emit()
        return True

    def clear(self):
        if not self._entries:
            return False
        self.beginResetModel()
        self._entries.clear()
        self.endResetModel()
        self.countChanged.emit()
        return True


class NotificationService(QObject):
    notificationsChanged = Signal()
    popupQueueChanged = Signal()
    unreadCountChanged = Signal()
    _notificationReceived = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications = []
        self._popup_model = PopupQueueModel(self)
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._notificationReceived.connect(self._commit_notification)

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
        with self._id_lock:
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

        # D-Bus calls arrive on the asyncio worker thread.  Deliver the model
        # mutation to this QObject's (GUI) thread before QML observes it.
        self._notificationReceived.emit(entry)
        return notif_id

    @Slot(object)
    def _commit_notification(self, entry):
        self._notifications.insert(0, entry)
        self._popup_model.prepend(entry)
        self.notificationsChanged.emit()
        self.popupQueueChanged.emit()
        self.unreadCountChanged.emit()

    @Property("QVariantList", notify=notificationsChanged)
    def notifications(self):
        return self._notifications

    @Property("QVariantList", notify=popupQueueChanged)
    def popupQueue(self):
        return self._popup_model.entries

    @Property(QObject, constant=True)
    def popupModel(self):
        return self._popup_model

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
        self._popup_model.clear()
        self.notificationsChanged.emit()
        self.popupQueueChanged.emit()
        self.unreadCountChanged.emit()

    @Slot("QVariant")
    def removeFromQueue(self, entry):
        if hasattr(entry, "toVariant"):
            entry = entry.toVariant()
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        if entry_id is not None and self._popup_model.remove_by_id(entry_id):
            self.popupQueueChanged.emit()

    @Slot(int)
    def removeFromQueueById(self, notification_id):
        if self._popup_model.remove_by_id(notification_id):
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
