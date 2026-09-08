"""Event-driven EWMH fullscreen detection on a worker-owned X connection."""
import select
import socket
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, Qt


def intersects(a, b):
    x, y, w, h = a
    bx, by, bw, bh = b
    return w > 0 and h > 0 and x < bx + bw and bx < x + w and y < by + bh and by < y + h


class FullscreenService(QObject):
    hasFullscreenChanged = Signal()
    _ready = Signal(bool)
    windowsRemoved = Signal("QVariantList")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_fullscreen = False
        self._stopped = threading.Event()
        self._screen = None
        self._wake_read, self._wake_write = socket.socketpair()
        self._wake_write.setblocking(False)
        self._ready.connect(self._apply, Qt.ConnectionType.QueuedConnection)
        self._thread = threading.Thread(target=self._run, name="sadeshell-fullscreen", daemon=True)
        self._thread.start()

    hasFullscreen = Property(bool, lambda self: self._has_fullscreen, notify=hasFullscreenChanged)

    @Slot(bool)
    def _apply(self, value):
        if not self._stopped.is_set() and value != self._has_fullscreen:
            self._has_fullscreen = value
            self.hasFullscreenChanged.emit()

    @Slot(int, int, int, int)
    def setScreenGeometry(self, x, y, width, height):
        self._screen = (x, y, width, height)
        if not self._stopped.is_set():
            try:
                self._wake_write.send(b"x")
            except BlockingIOError:
                pass  # A wake-up is already pending.

    def stop(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        try:
            self._wake_write.send(b"x")
        except BlockingIOError:
            pass
        self._thread.join(timeout=3)
        if not self._thread.is_alive():
            self._wake_read.close()
            self._wake_write.close()

    def _run(self):
        from Xlib import X, display
        connection = None
        try:
            connection = display.Display()
            root = connection.screen().root
            names = ["_NET_CLIENT_LIST", "_NET_WM_STATE", "_NET_WM_STATE_FULLSCREEN",
                     "_NET_WM_STATE_HIDDEN", "_NET_CURRENT_DESKTOP", "_NET_WM_DESKTOP"]
            atoms = {name: connection.intern_atom(name) for name in names}
            root.change_attributes(event_mask=X.PropertyChangeMask | X.SubstructureNotifyMask | X.StructureNotifyMask)
            cache = {}
            parents = {}
            members = set()
            desktop = 0
            root_geometry = root.get_geometry()
            bounds = (0, 0, root_geometry.width, root_geometry.height)

            def prop(window, name):
                value = window.get_full_property(atoms[name], X.AnyPropertyType)
                return list(value.value) if value is not None else []

            def snapshot(win_id):
                try:
                    window = connection.create_resource_object("window", win_id)
                    window.change_attributes(event_mask=X.PropertyChangeMask | X.StructureNotifyMask)
                    attrs = window.get_attributes()
                    geometry = window.get_geometry()
                    translated = root.translate_coords(window, 0, 0)
                    parent = window.query_tree().parent
                    for previous, child in list(parents.items()):
                        if child == win_id and previous != parent.id:
                            parents.pop(previous, None)
                    if parent.id != root.id:
                        parents[parent.id] = win_id
                        parent.change_attributes(event_mask=X.StructureNotifyMask)
                    state = prop(window, "_NET_WM_STATE")
                    cache[win_id] = (attrs.map_state == X.IsViewable,
                                     atoms["_NET_WM_STATE_FULLSCREEN"] in state,
                                     atoms["_NET_WM_STATE_HIDDEN"] in state,
                                     prop(window, "_NET_WM_DESKTOP"),
                                     (translated.x, translated.y, geometry.width, geometry.height))
                except Exception:
                    cache.pop(win_id, None)

            def membership():
                nonlocal members
                clients = set(prop(root, "_NET_CLIENT_LIST"))
                removed = members - clients
                members = clients
                if removed:
                    self.windowsRemoved.emit(sorted(removed))
                for win_id in removed:
                    cache.pop(win_id, None)
                for parent, child in list(parents.items()):
                    if child not in clients:
                        parents.pop(parent, None)
                for win_id in clients - set(cache):
                    snapshot(win_id)

            membership()
            current = prop(root, "_NET_CURRENT_DESKTOP")
            desktop = current[0] if current else 0
            while not self._stopped.is_set():
                screen = self._screen or bounds
                self._ready.emit(any(mapped and fullscreen and not hidden and
                                     (not desktops or desktops[0] in (desktop, 0xffffffff)) and
                                     intersects(geometry, screen)
                                     for mapped, fullscreen, hidden, desktops, geometry in cache.values()))
                connection.flush()
                if not connection.pending_events():
                    readable, _, _ = select.select([connection.fileno(), self._wake_read], [], [])
                    if self._wake_read in readable:
                        self._wake_read.recv(4096)
                affected = set()
                for _ in range(128):
                    if not connection.pending_events():
                        break
                    event = connection.next_event()
                    win_id = getattr(getattr(event, "window", None), "id", 0)
                    if win_id == root.id:
                        if event.type == X.PropertyNotify and event.atom == atoms["_NET_CLIENT_LIST"]:
                            membership()
                        elif event.type == X.PropertyNotify and event.atom == atoms["_NET_CURRENT_DESKTOP"]:
                            current = prop(root, "_NET_CURRENT_DESKTOP")
                            desktop = current[0] if current else 0
                        elif event.type == X.ConfigureNotify:
                            bounds = (0, 0, event.width, event.height)
                            affected.update(cache)
                    elif win_id in cache or win_id in parents:
                        affected.add(parents.get(win_id, win_id))
                for win_id in affected:
                    snapshot(win_id)
        except Exception as exc:
            if not self._stopped.is_set():
                print(f"Fullscreen detection unavailable: {exc}", flush=True)
        finally:
            if connection:
                connection.close()
