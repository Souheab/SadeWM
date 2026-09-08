"""NotificationService — D-Bus notification server."""

import asyncio
import threading
import time
from collections import OrderedDict

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
    QTimer,
)

try:
    from dbus_next.service import ServiceInterface, method, signal as dbus_signal
    from dbus_next import BusType
    from ..shared.async_bus import BusWorker
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
        self.insert(0, entry)

    def insert(self, row, entry):
        self.beginInsertRows(QModelIndex(), row, row)
        self._entries.insert(row, entry)
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
    notificationClosed = Signal(int, int)
    toastExpired = Signal(int)
    _notificationReceived = Signal(object)
    _closeReceived = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications = []
        self._active = OrderedDict()
        self._popup_model = PopupQueueModel(self)
        self._next_id = 1
        self._known_ids = set()
        self._id_lock = threading.Lock()
        self._stopped = False
        self._server_future = None
        self._dbus_iface = None
        self._bus_worker = None
        self._popup_sync_timer = QTimer(self)
        self._popup_sync_timer.setSingleShot(True)
        self._popup_sync_timer.timeout.connect(self._sync_popups)
        self._notificationReceived.connect(self._commit_notification)
        self._closeReceived.connect(self._close_from_dbus, Qt.ConnectionType.QueuedConnection)
        self.notificationClosed.connect(self._forward_closed)
        if HAS_DBUS:
            self._start_server()

    def _start_server(self):
        self._bus_worker = BusWorker.shared()
        self._server_future = self._bus_worker.submit(self._serve())

    async def _serve(self):
        bus = await self._bus_worker.connection(BusType.SESSION)
        iface = NotificationDBusInterface(self)
        self._dbus_iface = iface
        bus.export("/org/freedesktop/Notifications", iface)
        try:
            await asyncio.wait_for(bus.request_name("org.freedesktop.Notifications"), 10)
            await self._bus_worker.wait_disconnected(bus)
        finally:
            self._dbus_iface = None
            bus.unexport("/org/freedesktop/Notifications", iface)
            if bus.connected:
                await bus.release_name("org.freedesktop.Notifications")

    @Slot(int)
    def _close_from_dbus(self, ident):
        self._close(ident, 3)

    @Slot(int, int)
    def _forward_closed(self, ident, reason):
        iface = self._dbus_iface
        if iface is not None and self._bus_worker is not None:
            def emit_closed():
                if self._dbus_iface is iface:
                    iface.NotificationClosed(ident, reason)
            self._bus_worker.loop.call_soon_threadsafe(emit_closed)

    def _add_notification(self, app_name, summary, body, app_icon, expire_timeout, replaces_id=0):
        with self._id_lock:
            if replaces_id and replaces_id in self._known_ids:
                ident = replaces_id
            else:
                ident = self._next_id
                self._next_id += 1
                self._known_ids.add(ident)
        entry = dict(id=ident, summary=summary or "", body=body or "",
                     appName=app_name or "", appIcon=app_icon or "", image="",
                     expireTimeout=5000 if expire_timeout < 0 else expire_timeout)
        self._notificationReceived.emit(entry)
        return ident

    @Slot(object)
    def _commit_notification(self, entry):
        if self._stopped:
            return
        ident = entry["id"]
        previous = self._active.get(ident)
        shown = previous is not None and previous["shown"]
        paused = previous is not None and previous["paused"]
        if previous:
            previous["timer"].stop()
            previous["timer"].deleteLater()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setProperty("notificationId", ident)
        timer.timeout.connect(self._expire)
        self._active[ident] = dict(entry=entry, timer=timer, shown=shown, paused=paused,
                                   remaining=entry["expireTimeout"], deadline=0)
        for index, old in enumerate(self._notifications):
            if old["id"] == ident:
                self._notifications[index] = entry
                break
        else:
            self._notifications.insert(0, entry)
        while len(self._notifications) > 200:
            oldest = self._notifications.pop()
            self._close(oldest["id"], 4)
        while len(self._active) > 200:
            self._close(next(iter(self._active)), 4)
        self._sync_popups()
        if shown and not paused:
            self._arm(ident)
        self._notify()

    @Slot()
    def _expire(self):
        timer = self.sender()
        if timer is not None and not self._stopped:
            self._close(timer.property("notificationId"), 1, animate=True)

    def _notify(self):
        self.notificationsChanged.emit()
        self.popupQueueChanged.emit()
        self.unreadCountChanged.emit()

    @Slot()
    def _sync_popups(self):
        if self._stopped:
            return
        desired = [state["entry"] for state in reversed(self._active.values())][:5]
        desired_ids = {entry["id"] for entry in desired}
        for entry in list(self._popup_model.entries):
            if entry["id"] not in desired_ids:
                self.setPaused(entry["id"], True)
                self._popup_model.remove_by_id(entry["id"])
        current_ids = {entry["id"] for entry in self._popup_model.entries}
        for position, entry in enumerate(desired):
            if entry["id"] not in current_ids:
                self._popup_model.insert(position, entry)
            else:
                row = next(i for i, old in enumerate(self._popup_model.entries) if old["id"] == entry["id"])
                if self._popup_model.entries[row] != entry:
                    self._popup_model.entries[row] = entry
                    index = self._popup_model.index(row, 0)
                    self._popup_model.dataChanged.emit(index, index, [self._popup_model.NotificationRole])
        self.popupQueueChanged.emit()

    def _arm(self, ident):
        state = self._active.get(ident)
        if state and state["shown"] and not state["paused"] and state["entry"]["expireTimeout"] != 0:
            remaining = max(1, state["remaining"])
            state["deadline"] = time.monotonic() + remaining / 1000
            state["timer"].start(min(remaining, 2147483647))

    @Slot(int)
    def toastShown(self, ident):
        state = self._active.get(ident)
        if state:
            state["shown"] = True
            state["paused"] = False
            self._arm(ident)

    @Slot(int, bool)
    def setPaused(self, ident, paused):
        state = self._active.get(ident)
        if not state or state["paused"] == paused:
            return
        state["paused"] = paused
        if paused:
            if state["timer"].isActive():
                state["remaining"] = max(1, int((state["deadline"] - time.monotonic()) * 1000))
                state["timer"].stop()
        else:
            self._arm(ident)

    def _close(self, ident, reason, animate=False):
        state = self._active.pop(ident, None)
        if state:
            state["timer"].stop()
            state["timer"].deleteLater()
            with self._id_lock:
                self._known_ids.discard(ident)
            self.notificationClosed.emit(ident, reason)
        if reason != 1:
            self._notifications = [entry for entry in self._notifications if entry["id"] != ident]
        if animate and state:
            self.toastExpired.emit(ident)
            self._popup_sync_timer.start(300)
        else:
            self._sync_popups()
        self._notify()

    notifications = Property("QVariantList", lambda self: self._notifications, notify=notificationsChanged)
    popupQueue = Property("QVariantList", lambda self: self._popup_model.entries, notify=popupQueueChanged)
    popupModel = Property(QObject, lambda self: self._popup_model, constant=True)
    unreadCount = Property(int, lambda self: len(self._notifications), notify=unreadCountChanged)

    @Slot(int)
    def dismiss(self, index):
        if 0 <= index < len(self._notifications):
            self._close(self._notifications[index]["id"], 2)

    @Slot()
    def dismissAll(self):
        for ident in list(self._active):
            self._close(ident, 2)
        self._notifications.clear()
        self._popup_model.clear()
        self._notify()

    @Slot("QVariant")
    def removeFromQueue(self, entry):
        if hasattr(entry, "toVariant"):
            entry = entry.toVariant()
        if isinstance(entry, dict) and "id" in entry:
            self.removeFromQueueById(entry["id"])

    @Slot(int)
    def removeFromQueueById(self, ident):
        if ident in self._active:
            self._close(ident, 2)
        else:
            self._sync_popups()

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self._popup_sync_timer.stop()
        for state in self._active.values():
            state["timer"].stop()
        self._active.clear()
        self._notifications.clear()
        self._popup_model.clear()
        with self._id_lock:
            self._known_ids.clear()
        if self._server_future:
            self._server_future.cancel()


if HAS_DBUS:
    class NotificationDBusInterface(ServiceInterface):
        def __init__(self, service):
            super().__init__("org.freedesktop.Notifications")
            self._service = service

        @method()
        def GetCapabilities(self) -> 'as':  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
            return ["body", "body-markup", "persistence"]

        @method()
        def GetServerInformation(self) -> 'ssss':  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
            return ["sadeshell", "sadeshell", "0.1", "1.2"]

        @method()
        def Notify(self, app_name: 's', replaces_id: 'u', app_icon: 's',  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
                   summary: 's', body: 's', actions: 'as',  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
                   hints: 'a{sv}', expire_timeout: 'i') -> 'u':  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
            notif_id = self._service._add_notification(
                app_name, summary, body, app_icon, expire_timeout, replaces_id
            )
            return notif_id

        @method()
        def CloseNotification(self, id: 'u'):  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
            self._service._closeReceived.emit(id)

        @dbus_signal()
        def NotificationClosed(self, id: 'u', reason: 'u') -> 'uu':  # noqa: F821, F722 -- D-Bus wire signatures, not Python types
            return [id, reason]
