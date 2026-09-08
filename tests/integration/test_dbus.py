import asyncio
import os
import time

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next import BusType, PropertyAccess
from PySide6.QtCore import QCoreApplication

from sadeshell.services.shared.async_bus import AsyncService, BusWorker, ObjectMonitor, OBJECTS, call, DBUS

NAME = "org.sadeshell.TestObjects"
INTERFACE = "org.sadeshell.TestDevice"


class Device(ServiceInterface):
    def __init__(self, value):
        super().__init__(INTERFACE)
        self.value = value

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "s":  # noqa: F821 -- D-Bus signature
        return self.value


class Manager(ServiceInterface):
    def __init__(self, value):
        super().__init__(OBJECTS)
        self.value = value

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # noqa: F722 -- D-Bus signature
        return {"/device": {INTERFACE: {"Value": Variant("s", self.value)}}}

    @signal()
    def InterfacesAdded(self, path, interfaces) -> "oa{sa{sv}}":  # noqa: F722 -- D-Bus signature
        return [path, interfaces]


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_object_subscriptions_recover_from_owner_and_bus_replacement(monkeypatch):
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", os.environ["DBUS_SESSION_BUS_ADDRESS"])
    worker = BusWorker()
    class Service(AsyncService):
        def __init__(self):
            super().__init__(worker=worker)
            self.values = []
            self.monitor = ObjectMonitor(self, NAME, "/")
        def apply_state(self, state):
            self.values.append(state["/device"][INTERFACE]["Value"])
    service = Service()
    servers = []

    async def server(value):
        bus = await MessageBus().connect()
        manager = Manager(value)
        bus.export("/", manager)
        bus.export("/device", Device(value))
        await bus.request_name(NAME)
        servers.append(bus)
        return bus, manager

    try:
        bus, manager = worker.submit(server("first")).result(timeout=3)
        service.start_task(service.monitor.run())
        wait_for(lambda: service.values == ["first"])

        async def change():
            manager.InterfacesAdded("/device", {INTERFACE: {"Value": Variant("s", "changed")}})
        worker.submit(change()).result(timeout=3)
        wait_for(lambda: service.values[-1] == "changed")

        async def replace():
            await bus.release_name(NAME)
            bus.disconnect()
            await server("replacement")
        worker.submit(replace()).result(timeout=3)
        wait_for(lambda: service.values[-1] == "replacement")
        before_idle = len(service.values)
        until = time.monotonic() + 0.2
        while time.monotonic() < until:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        assert len(service.values) <= before_idle + 1  # no reconnect loop after owner replacement
        old_connection = worker.buses[BusType.SYSTEM]
        before = len(service.values)
        worker.loop.call_soon_threadsafe(old_connection.disconnect)
        wait_for(lambda: worker.buses.get(BusType.SYSTEM) is not old_connection and
                 len(service.values) > before and service.values[-1] == "replacement")
        assert worker.buses[BusType.SYSTEM] is not old_connection
        assert service.available
    finally:
        service.stop()
        async def close_servers():
            for bus in servers:
                bus.disconnect()
            await asyncio.sleep(0)
        worker.submit(close_servers()).result(timeout=3)
        worker.stop()


def test_notification_close_signal_is_emitted_once_on_the_bus():
    from sadeshell.services.bar.notification_service import NotificationService
    service = NotificationService()
    worker = service._bus_worker
    received = []
    bus = None
    async def connect():
        client = await MessageBus().connect()
        client.add_message_handler(lambda message: received.append(message.body)
                                   if message.interface == "org.freedesktop.Notifications" and
                                   message.member == "NotificationClosed" else None)
        await call(client, DBUS, "/org/freedesktop/DBus", DBUS, "AddMatch",
                   "s", ["type='signal',interface='org.freedesktop.Notifications'"])
        return client
    try:
        wait_for(lambda: service._dbus_iface is not None)
        bus = worker.submit(connect()).result(timeout=3)
        async def notify():
            return await call(bus, "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                              "org.freedesktop.Notifications", "Notify", "susssasa{sv}i",
                              ["tests", 0, "", "title", "body", [], {}, 0])
        ident = worker.submit(notify()).result(timeout=3)[0]
        wait_for(lambda: ident in service._active)
        async def close():
            for _ in range(2):
                await call(bus, "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                           "org.freedesktop.Notifications", "CloseNotification", "u", [ident])
        worker.submit(close()).result(timeout=3)
        wait_for(lambda: received == [[ident, 3]])
        assert not service._active
        assert not service.notifications
    finally:
        if bus:
            worker.loop.call_soon_threadsafe(bus.disconnect)
        service.stop()
        worker.stop()
