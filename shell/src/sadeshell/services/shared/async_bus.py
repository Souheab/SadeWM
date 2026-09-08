"""One asyncio thread and two reusable buses. No Qt state is changed here."""
import asyncio
import json
import threading

from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from PySide6.QtCore import QObject, Property, Signal, Slot, Qt

DBUS = "org.freedesktop.DBus"
PROPS = DBUS + ".Properties"
OBJECTS = DBUS + ".ObjectManager"
CALL_TIMEOUT = 10


def unpack(value):
    if isinstance(value, Variant):
        return unpack(value.value)
    if isinstance(value, dict):
        return {k: unpack(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, bytes)):
        return [unpack(v) for v in value]
    return value


async def call(bus, destination, path, interface, member, signature="", body=()):
    reply = await asyncio.wait_for(bus.call(Message(
        destination=destination, path=path, interface=interface, member=member,
        signature=signature, body=list(body))), CALL_TIMEOUT)
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"{reply.error_name}: {reply.body[0] if reply.body else member}")
    return unpack(reply.body)


class BusWorker:
    _instance = None

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.buses = {}
        self.disconnects = {}
        self.locks = {}
        self.thread = threading.Thread(target=self._run, name="sadeshell-dbus", daemon=True)
        self.thread.start()
        self.stopped = False

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    def submit(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    async def connection(self, kind):
        async with self.locks.setdefault(kind, asyncio.Lock()):
            bus = self.buses.get(kind)
            if bus is not None and bus.connected:
                return bus
            if bus is not None:
                self.disconnects.pop(bus, None)
            bus = MessageBus(bus_type=kind)
            try:
                await asyncio.wait_for(bus.connect(), 10)
                await call(bus, DBUS, "/org/freedesktop/DBus", DBUS, "AddMatch",
                           "s", ["type='signal'"])
            except BaseException:
                bus.disconnect()
                raise
            self.buses[kind] = bus
            disconnected = asyncio.create_task(bus.wait_for_disconnect())
            disconnected.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
            self.disconnects[bus] = disconnected
            return bus

    async def wait_disconnected(self, bus):
        # One waiter per physical connection. Canceling a service subscription
        # must not cancel the bus's shared disconnect future.
        await asyncio.shield(self.disconnects[bus])

    def stop(self):
        if self.stopped:
            return
        self.stopped = True

        async def shutdown():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for bus in self.buses.values():
                bus.disconnect()
        try:
            self.submit(shutdown()).result(timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
            BusWorker._instance = None


class AsyncService(QObject):
    """Qt-facing status and immutable result delivery shared by bus services."""
    statusChanged = Signal()
    _result = Signal(str)

    def __init__(self, parent=None, worker=None):
        super().__init__(parent)
        self.worker = worker or BusWorker.shared()
        self._stopped = False
        self._available = False
        self._busy = 0
        self._error = ""
        self._futures = set()
        self._result.connect(self._receive, Qt.ConnectionType.QueuedConnection)

    available = Property(bool, lambda self: self._available, notify=statusChanged)
    busy = Property(bool, lambda self: self._busy > 0, notify=statusChanged)
    error = Property(str, lambda self: self._error, notify=statusChanged)

    def publish(self, **data):
        if not self._stopped:
            self._result.emit(json.dumps(data))

    @Slot(str)
    def _receive(self, encoded):
        if self._stopped:
            return
        data = json.loads(encoded)
        if "revision" in data and data["revision"] != self.monitor.revision:
            return
        if "done" in data:
            self._busy = max(0, self._busy - 1)
        self._available = data.get("available", self._available)
        self._error = data.get("error", self._error)
        self.statusChanged.emit()
        if "state" in data:
            self.apply_state(data["state"])

    def start_task(self, coroutine):
        future = self.worker.submit(coroutine)
        self._futures.add(future)
        return future

    def command(self, coroutine, key="default"):
        if self._stopped:
            coroutine.close()
            return
        self._busy += 1
        self._error = ""
        self.statusChanged.emit()

        async def run():
            try:
                async with self.worker.locks.setdefault((id(self), key), asyncio.Lock()):
                    await asyncio.wait_for(coroutine, 45)
                self.publish(done=True, error="")
            except asyncio.CancelledError:
                coroutine.close()
                raise
            except Exception as exc:
                self.publish(done=True, error=str(exc) or "Operation timed out; please retry")
        self._futures = {f for f in self._futures if not f.done()}
        self.start_task(run())

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        for future in self._futures:
            future.cancel()
        self._futures.clear()


class ObjectMonitor:
    """Own an ObjectManager snapshot, replay signals received during the snapshot."""
    def __init__(self, service, name, path):
        self.service, self.name, self.path = service, name, path
        self.objects = {}
        self.owner = None
        self.bus = None
        self.changed = asyncio.Event()
        self.revision = 0

    async def run(self):
        delay = 1
        while True:
            bus = None
            disconnected = None
            queue = asyncio.Queue()
            def handler(message):
                if message.message_type == MessageType.SIGNAL:
                    if message.interface == DBUS and message.member == "NameOwnerChanged" and message.body[0] == self.name:
                        self.revision += 1
                        self.owner = None
                        self.changed.set()
                    queue.put_nowait(message)
            try:
                bus = await self.service.worker.connection(BusType.SYSTEM)
                self.bus = bus
                bus.add_message_handler(handler)
                async def watch_disconnect(watched_bus=bus, outgoing=queue):
                    try:
                        await self.service.worker.wait_disconnected(watched_bus)
                    except Exception:
                        pass
                    finally:
                        outgoing.put_nowait(None)
                disconnected = asyncio.create_task(watch_disconnect())
                revision = self.revision
                self.owner = (await call(bus, DBUS, "/org/freedesktop/DBus", DBUS,
                                         "GetNameOwner", "s", [self.name]))[0]
                self.objects = (await call(bus, self.owner, self.path, OBJECTS, "GetManagedObjects"))[0]
                if revision != self.revision:
                    continue
                self.emit()
                delay = 1
                while bus.connected:
                    message = await queue.get()
                    if message is None:
                        break
                    if message.interface == DBUS and message.member == "NameOwnerChanged" and message.body[0] == self.name:
                        break
                    if message.sender != self.owner:
                        continue
                    body = unpack(message.body)
                    if message.interface == OBJECTS and message.member == "InterfacesAdded":
                        self.objects.setdefault(body[0], {}).update(body[1])
                    elif message.interface == OBJECTS and message.member == "InterfacesRemoved":
                        for interface in body[1]:
                            self.objects.get(body[0], {}).pop(interface, None)
                        if not self.objects.get(body[0]):
                            self.objects.pop(body[0], None)
                    elif message.interface == PROPS and message.member == "PropertiesChanged":
                        props = self.objects.setdefault(message.path, {}).setdefault(body[0], {})
                        props.update(body[1])
                        for key in body[2]:
                            props.pop(key, None)
                            props[key] = (await call(bus, self.owner, message.path, PROPS, "Get", "ss", [body[0], key]))[0]
                    else:
                        continue
                    self.changed.set()
                    self.emit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.service.publish(available=False, error=str(exc) or f"{self.name} did not reply in time")
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)
            finally:
                self.owner = None
                if disconnected:
                    disconnected.cancel()
                if bus is not None:
                    bus.remove_message_handler(handler)

    def emit(self):
        if self.owner is not None:
            self.service.publish(available=True, error="", state=self.objects, revision=self.revision)

    async def invoke(self, path, interface, member, signature="", body=()):
        owner, bus = self.owner, self.bus
        if not owner or not bus or not bus.connected:
            raise RuntimeError(f"{self.name} is unavailable")
        result = await call(bus, owner, path, interface, member, signature, body)
        if owner != self.owner:
            raise RuntimeError("Service restarted; please retry")
        return result
