"""WindowPickerService — exposes active and minimized windows to picker popups.

Uses:
- sadewm IPC socket to enumerate clients (get_clients) and focus them (focus_window)
- python-xlib to read _NET_WM_ICON for per-window icons, with XDG theme fallback
- python-xlib get_image() + Pillow for window thumbnails (no external tools needed)
- Images are saved to a private per-process runtime directory and exposed as file:// URIs
"""

from __future__ import annotations

import atexit
import json
import os

from .icon_index import icons
import shutil
import socket
import stat
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse
from collections import OrderedDict

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Signal,
    Slot,
    Qt,
)

# Cache for saved thumbnails and icons. It is created lazily so starting the
# shell never leaves an empty directory behind when the picker is unused.
_CACHE_DIR: str | None = None
_CACHE_CLOSED = False
_CACHE_LOCK = threading.RLock()
_OWNED_FILES = OrderedDict()


def _private_runtime_parent() -> str:
    """Return a trustworthy runtime parent, falling back to the system temp dir."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        try:
            info = os.stat(runtime_dir, follow_symlinks=False)
            if (
                stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.getuid()
                and (stat.S_IMODE(info.st_mode) & 0o022) == 0
            ):
                return runtime_dir
        except OSError:
            pass
    return tempfile.gettempdir()


def _create_private_cache_dir(parent: str | None = None) -> str:
    cache_dir = tempfile.mkdtemp(
        prefix="sadeshell-winpicker-",
        dir=parent or _private_runtime_parent(),
    )
    os.chmod(cache_dir, 0o700)
    return cache_dir


def _get_cache_dir() -> str:
    global _CACHE_DIR
    with _CACHE_LOCK:
        if _CACHE_CLOSED:
            raise RuntimeError("window picker cache is closed")
        if _CACHE_DIR is None:
            _CACHE_DIR = _create_private_cache_dir()
        return _CACHE_DIR


def _write_private_png(image, cache_dir: str, filename: str) -> str:
    """Atomically save a PNG with permissions restricted to the current user."""
    fd, temporary_path = tempfile.mkstemp(
        prefix=".sadeshell-image-",
        suffix=".png",
        dir=cache_dir,
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            fd = -1
            image.save(output, "PNG")
        destination = os.path.join(cache_dir, filename)
        os.replace(temporary_path, destination)
        os.chmod(destination, 0o600)
        return destination
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _save_cached_png(image, filename: str) -> str:
    # Keep cleanup from racing a capture that is encoding or replacing a file.
    with _CACHE_LOCK:
        path = _write_private_png(image, _get_cache_dir(), filename)
        _OWNED_FILES[path] = os.path.getsize(path)
        while len(_OWNED_FILES) > 128 or sum(_OWNED_FILES.values()) > 32 * 1024 * 1024:
            old, _ = _OWNED_FILES.popitem(last=False)
            try:
                os.unlink(old)
            except FileNotFoundError:
                pass
        return path


def _remove_private_cache_dir(cache_dir: str) -> None:
    try:
        shutil.rmtree(cache_dir)
    except FileNotFoundError:
        pass


def _cleanup_cache() -> None:
    global _CACHE_DIR, _CACHE_CLOSED
    with _CACHE_LOCK:
        _CACHE_CLOSED = True
        cache_dir = _CACHE_DIR
        _CACHE_DIR = None
        if cache_dir is not None:
            _remove_private_cache_dir(cache_dir)


def _delete_owned_uri(uri):
    path = unquote(urlparse(uri).path)
    with _CACHE_LOCK:
        if path in _OWNED_FILES:
            _OWNED_FILES.pop(path)
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


atexit.register(_cleanup_cache)


# ---------------------------------------------------------------------------
# sadewm IPC helpers
# ---------------------------------------------------------------------------

def _get_sadewm_socket() -> str:
    if p := os.environ.get("SADEWM_SOCKET"):
        return p
    display = os.environ.get("DISPLAY", "")
    if display:
        safe = display.lstrip(":").replace(".", "-")
        return f"/tmp/sadewm-{safe}.sock"
    return "/tmp/sadewm.sock"


def _sadewm_request(request: dict) -> dict:
    path = _get_sadewm_socket()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(path)
            s.sendall(json.dumps(request).encode())
            s.shutdown(socket.SHUT_WR)
            data = b""
            while chunk := s.recv(65536):
                data += chunk
        return json.loads(data)
    except Exception:
        try:
            from .ewmh_client import request as ewmh_request
            return ewmh_request(request)
        except Exception:
            return {"ok": False}


# ---------------------------------------------------------------------------
# Icon resolution — _NET_WM_ICON then XDG theme fallback
# ---------------------------------------------------------------------------


_ICON_TARGET_SIZE = 64

def _icon_path_from_class(wm_class):
    return icons.resolve(wm_class)


def _net_wm_icon_file_uri(win_id, wm_class, cache_token=None):
    try:
        image = _capture_connection().icon(win_id)
        if image is not None:
            token = cache_token if cache_token is not None else time.monotonic_ns()
            return "file://" + _save_cached_png(image, f"icon_{win_id}_{token}.png")
    except Exception:
        pass
    path = _icon_path_from_class(wm_class)
    return "file://" + path if path else ""


# ---------------------------------------------------------------------------
# Thumbnail capture via python-xlib get_image + Pillow
# ---------------------------------------------------------------------------

_THUMB_W = 212
_THUMB_H = 136


_CAPTURE_LOCAL = threading.local()
_CAPTURE_CONNECTIONS = []
_CAPTURE_CONNECTIONS_LOCK = threading.Lock()


def _capture_connection():
    from .thumbnail_capture import CaptureConnection
    capture = getattr(_CAPTURE_LOCAL, "connection", None)
    if capture is None:
        capture = CaptureConnection()
        _CAPTURE_LOCAL.connection = capture
        with _CAPTURE_CONNECTIONS_LOCK:
            _CAPTURE_CONNECTIONS.append(capture)
    return capture


def _capture_thumbnail_file_uri(win_id, cache_token=None):
    try:
        capture = _capture_connection()
        image = capture.capture(win_id)
        if image is None:
            return ""
        token = cache_token if cache_token is not None else time.monotonic_ns()
        return "file://" + _save_cached_png(image, f"thumb_{win_id}_{token}.png")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# WindowPickerService
# ---------------------------------------------------------------------------


_WINDOW_ROLES = (
    "winId",
    "name",
    "wmClass",
    "tags",
    "tagNum",
    "workspaceLabel",
    "focused",
    "minimized",
    "iconUri",
    "thumbnailUri",
)


class WindowListModel(QAbstractListModel):
    """Filterable window model whose asset roles can be updated per row."""

    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        first_role = int(Qt.ItemDataRole.UserRole) + 1
        self._role_names = {
            first_role + index: name.encode()
            for index, name in enumerate(_WINDOW_ROLES)
        }
        self._role_ids = {
            name.decode(): role for role, name in self._role_names.items()
        }
        self._all_items: list[dict] = []
        self._items: list[dict] = []
        self._query = ""

    def roleNames(self):
        return self._role_names

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        role_name = self._role_names.get(role)
        if role_name is None:
            return None
        return self._items[index.row()].get(role_name.decode())

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._items)

    @Slot(int, result="QVariantMap")
    def get(self, row):
        if 0 <= row < len(self._items):
            return dict(self._items[row])
        return {}

    @Slot(str)
    def setFilter(self, query):
        normalized = (query or "").strip().casefold()
        if normalized == self._query:
            return
        self._query = normalized
        self._reset_visible_items()

    def set_items(self, items):
        incoming = [dict(item) for item in items]
        same_rows = (
            not self._query
            and len(incoming) == len(self._all_items)
            and [
                item.get("winId") for item in incoming
            ] == [
                item.get("winId") for item in self._all_items
            ]
        )
        if same_rows:
            for row, (current, replacement) in enumerate(
                zip(self._all_items, incoming)
            ):
                changed_names = [
                    name
                    for name in _WINDOW_ROLES
                    if current.get(name) != replacement.get(name)
                ]
                current.clear()
                current.update(replacement)
                if changed_names:
                    roles = [self._role_ids[name] for name in changed_names]
                    model_index = self.index(row, 0)
                    self.dataChanged.emit(
                        model_index, model_index, roles
                    )
            return
        self.beginResetModel()
        self._all_items = incoming
        self._items = self._filtered_items()
        self.endResetModel()
        self.countChanged.emit()

    def update_item(self, win_id, changes):
        changed_names = [name for name in changes if name in self._role_ids]
        if not changed_names:
            return
        target = None
        for item in self._all_items:
            if item.get("winId") == win_id:
                item.update(changes)
                target = item
                break
        if target is None:
            return
        for row, item in enumerate(self._items):
            if item is target:
                roles = [self._role_ids[name] for name in changed_names]
                model_index = self.index(row, 0)
                self.dataChanged.emit(model_index, model_index, roles)
                break

    def _filtered_items(self):
        if not self._query:
            return list(self._all_items)
        return [
            item
            for item in self._all_items
            if self._query in str(item.get("name", "")).casefold()
            or self._query in str(item.get("wmClass", "")).casefold()
        ]

    def _reset_visible_items(self):
        self.beginResetModel()
        self._items = self._filtered_items()
        self.endResetModel()
        self.countChanged.emit()


@dataclass
class _WindowAssets:
    wm_class: str
    identity: int = field(default_factory=time.monotonic_ns)
    icon_uri: str = ""
    icon_attempted: bool = False
    thumbnail_uri: str = ""
    thumbnail_attempted_at: float = 0.0
    thumbnail_geometry: tuple[int, int] = (0, 0)


_VISIBLE_THUMBNAIL_TTL = 3.0
_BACKGROUND_THUMBNAIL_TTL = 30.0
_CAPTURE_WORKERS = 2


class WindowPickerService(QObject):
    """Provides active WM windows and minimized windows with cached assets.

    Normal and minimized pickers have independent models and notifications.
    """

    windowsChanged = Signal()
    minimizedWindowsChanged = Signal()
    refreshingChanged = Signal()
    minimizedRefreshingChanged = Signal()
    _windowsReady = Signal(int, object)
    _windowsFinished = Signal(int)
    _minimizedReady = Signal(int, object)
    _minimizedFinished = Signal(int)
    _assetReady = Signal(int, str, int, object)
    _captureDone = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stopped = False
        self._requested = {"normal": set(), "minimized": set()}
        self._inflight = {}
        self._pending = {}
        self._windows: list[dict] = []
        self._minimized_windows: list[dict] = []
        self._windows_model = WindowListModel(self)
        self._minimized_windows_model = WindowListModel(self)
        self._asset_cache: dict[int, _WindowAssets] = {}
        self._asset_cache_lock = threading.Lock()
        self._capture_pool = ThreadPoolExecutor(
            max_workers=_CAPTURE_WORKERS,
            thread_name_prefix="sadeshell-window-assets",
        )
        self._refresh_generation = 0
        self._refresh_running = False
        self._refresh_pending = False
        self._minimized_generation = 0
        self._minimized_running = False
        self._minimized_pending = False
        self._focus_history: list[int] = []
        self._focus_history_lock = threading.Lock()

        self._captureDone.connect(self._finish_capture, Qt.ConnectionType.QueuedConnection)
        self._windowsReady.connect(
            self._apply_windows, Qt.ConnectionType.QueuedConnection
        )
        self._windowsFinished.connect(
            self._finish_refresh, Qt.ConnectionType.QueuedConnection
        )
        self._minimizedReady.connect(
            self._apply_minimized_windows, Qt.ConnectionType.QueuedConnection
        )
        self._minimizedFinished.connect(
            self._finish_minimized_refresh, Qt.ConnectionType.QueuedConnection
        )
        self._assetReady.connect(
            self._apply_asset, Qt.ConnectionType.QueuedConnection
        )

    @Property("QVariantList", notify=windowsChanged)
    def windows(self) -> list:
        return self._windows

    @Property("QVariantList", notify=minimizedWindowsChanged)
    def minimizedWindows(self) -> list:
        return self._minimized_windows

    @Property(QObject, constant=True)
    def windowsModel(self):
        return self._windows_model

    @Property(QObject, constant=True)
    def minimizedWindowsModel(self):
        return self._minimized_windows_model

    @Property(bool, notify=refreshingChanged)
    def refreshing(self):
        return self._refresh_running

    @Property(bool, notify=minimizedRefreshingChanged)
    def minimizedRefreshing(self):
        return self._minimized_running

    @Slot()
    def refresh(self):
        """Re-query all windows from the WM, capture thumbnails and icons."""
        self._refresh_generation += 1
        if self._refresh_running:
            self._refresh_pending = True
            return
        self._start_refresh(self._refresh_generation)

    def _start_refresh(self, generation):
        if not self._refresh_running:
            self._refresh_running = True
            self.refreshingChanged.emit()
        threading.Thread(
            target=self._do_refresh,
            args=(generation,),
            daemon=True,
            name="sadeshell-window-picker",
        ).start()

    def _do_refresh(self, generation):
        try:
            state_resp = _sadewm_request({"cmd": "get_state"})
            current_tags = (
                state_resp.get("tag_mask", 0) if state_resp.get("ok") else 0
            )
            resp = _sadewm_request({"cmd": "get_clients"})
            if not resp.get("ok"):
                self._windowsReady.emit(generation, [])
                return

            clients = resp.get("clients", [])
            self._purge_asset_cache({int(c.get("win_id", 0)) for c in clients})
            visible_clients = [
                client
                for client in clients
                if not client.get("minimized", False)
            ]
            visible_clients = self._order_by_recent_focus(visible_clients)
            result = [self._entry_from_client(c) for c in visible_clients]
            for entry in result:
                entry["_onCurrentTags"] = bool(entry["tags"] & current_tags)
            self._windowsReady.emit(generation, result)
            self._capture_assets(
                generation,
                "normal",
                result,
                current_tags=current_tags,
                include_thumbnails=True,
            )
        finally:
            self._windowsFinished.emit(generation)

    @Slot(int, object)
    def _apply_windows(self, generation, windows):
        if generation != self._refresh_generation:
            return
        self._windows = windows
        self._windows_model.set_items(windows)
        self.windowsChanged.emit()

    @Slot(int)
    def _finish_refresh(self, _generation):
        if self._refresh_pending:
            self._refresh_pending = False
            self._start_refresh(self._refresh_generation)
            return
        self._refresh_running = False
        self.refreshingChanged.emit()

    @Slot()
    def refreshMinimized(self):
        """Re-query minimized windows on currently selected tags."""
        self._minimized_generation += 1
        if self._minimized_running:
            self._minimized_pending = True
            return
        self._start_minimized_refresh(self._minimized_generation)

    def _start_minimized_refresh(self, generation):
        if not self._minimized_running:
            self._minimized_running = True
            self.minimizedRefreshingChanged.emit()
        threading.Thread(
            target=self._do_refresh_minimized,
            args=(generation,),
            daemon=True,
            name="sadeshell-minimized-picker",
        ).start()

    def _do_refresh_minimized(self, generation):
        try:
            # Get current tag mask from WM state
            state_resp = _sadewm_request({"cmd": "get_state"})
            current_tags = state_resp.get("tag_mask", 0) if state_resp.get("ok") else 0

            resp = _sadewm_request({"cmd": "get_clients"})
            if not resp.get("ok"):
                self._minimizedReady.emit(generation, [])
                return

            clients = resp.get("clients", [])

            # Filter minimized windows to the currently selected tags.
            result: list[dict] = []
            for c in clients:
                if not c.get("minimized", False):
                    continue
                win_tags = c.get("tags", 0)
                if current_tags != 0 and (win_tags & current_tags) == 0:
                    continue
                result.append(self._entry_from_client(c))

            self._minimizedReady.emit(generation, result)
            self._capture_assets(
                generation,
                "minimized",
                result,
                current_tags=current_tags,
                include_thumbnails=False,
            )
        finally:
            self._minimizedFinished.emit(generation)

    @Slot(int, object)
    def _apply_minimized_windows(self, generation, windows):
        if generation != self._minimized_generation:
            return
        self._minimized_windows = windows
        self._minimized_windows_model.set_items(windows)
        self.minimizedWindowsChanged.emit()

    def _entry_from_client(self, client):
        win_id = int(client.get("win_id", 0))
        wm_class = str(client.get("class", "") or "")
        tags = int(client.get("tags", 0))
        geometry = (
            int(client.get("width", 0) or 0),
            int(client.get("height", 0) or 0),
        )
        with self._asset_cache_lock:
            assets = self._asset_cache.get(win_id)
            if assets is None or assets.wm_class != wm_class:
                assets = _WindowAssets(wm_class=wm_class)
                self._asset_cache[win_id] = assets
            for field in ("icon_uri", "thumbnail_uri"):
                uri = getattr(assets, field)
                if uri.startswith("file://") and not os.path.isfile(unquote(urlparse(uri).path)):
                    setattr(assets, field, "")
                    if field == "icon_uri":
                        assets.icon_attempted = False
                    else:
                        assets.thumbnail_attempted_at = 0
            icon_uri = assets.icon_uri
            thumbnail_uri = assets.thumbnail_uri
        return {
            "winId": win_id,
            "name": str(client.get("name", "") or ""),
            "wmClass": wm_class,
            "tags": tags,
            "tagNum": (tags & -tags).bit_length() if tags else 0,
            "workspaceLabel": ", ".join(
                str(index + 1)
                for index in range(32)
                if tags & (1 << index)
            ),
            "focused": bool(client.get("focused", False)),
            "minimized": bool(client.get("minimized", False)),
            "iconUri": icon_uri,
            "thumbnailUri": thumbnail_uri,
            "_geometry": geometry,
            "_identity": assets.identity,
        }

    def _order_by_recent_focus(self, clients):
        """Keep the focused client first and the rest in MRU order when known."""
        active_ids = {
            int(client.get("win_id", 0))
            for client in clients
            if int(client.get("win_id", 0))
        }
        focused_ids = [
            int(client.get("win_id", 0))
            for client in clients
            if client.get("focused") and int(client.get("win_id", 0))
        ]
        with self._focus_history_lock:
            for win_id in reversed(focused_ids):
                if win_id in self._focus_history:
                    self._focus_history.remove(win_id)
                self._focus_history.insert(0, win_id)
            self._focus_history = [
                win_id
                for win_id in self._focus_history
                if win_id in active_ids
            ]
            rank = {
                win_id: index
                for index, win_id in enumerate(self._focus_history)
            }

        indexed_clients = list(enumerate(clients))
        indexed_clients.sort(
            key=lambda pair: (
                0 if pair[1].get("focused") else 1,
                rank.get(
                    int(pair[1].get("win_id", 0)),
                    len(rank) + pair[0],
                ),
                pair[0],
            )
        )
        return [client for _index, client in indexed_clients]

    def _remember_focused_window(self, win_id):
        if not win_id:
            return
        with self._focus_history_lock:
            if win_id in self._focus_history:
                self._focus_history.remove(win_id)
            self._focus_history.insert(0, win_id)

    def _purge_asset_cache(self, active_ids):
        with self._asset_cache_lock:
            stale_ids = set(self._asset_cache) - active_ids
            for win_id in stale_ids:
                assets = self._asset_cache.pop(win_id)
                _delete_owned_uri(assets.icon_uri)
                _delete_owned_uri(assets.thumbnail_uri)

    @Slot("QVariantList")
    def removeWindows(self, window_ids):
        removed = set(window_ids)
        with self._asset_cache_lock:
            for win_id in removed:
                assets = self._asset_cache.pop(win_id, None)
                if assets:
                    _delete_owned_uri(assets.icon_uri)
                    _delete_owned_uri(assets.thumbnail_uri)
                self._pending.pop(win_id, None)
        for target in self._requested:
            self._requested[target] -= removed
        self._windows = [entry for entry in self._windows if entry.get("winId") not in removed]
        self._minimized_windows = [entry for entry in self._minimized_windows if entry.get("winId") not in removed]
        self._windows_model.set_items(self._windows)
        self._minimized_windows_model.set_items(self._minimized_windows)
        self.windowsChanged.emit()
        self.minimizedWindowsChanged.emit()

    @staticmethod
    def _priority(entry, current_tags, original_index):
        if entry.get("focused"):
            group = 0
        elif current_tags and entry.get("tags", 0) & current_tags:
            group = 1
        else:
            group = 2
        return group, original_index

    @Slot(str, "QVariantList", bool)
    def setRequestedWindows(self, target, windowIds, active):
        if target not in self._requested or self._stopped:
            return
        self._requested[target] = set(int(w) for w in windowIds) if active else set()
        entries = self._windows if target == "normal" else self._minimized_windows
        generation = self._refresh_generation if target == "normal" else self._minimized_generation
        self._capture_assets(generation, target, entries, current_tags=0, include_thumbnails=target == "normal")

    def _capture_assets(self, generation, target, entries, *, current_tags, include_thumbnails):
        # Called by refresh workers in older callers: scheduling belongs to Qt.
        # Results trigger the QML viewport report after model publication.
        if threading.current_thread() is not threading.main_thread():
            return
        if self._stopped:
            return
        self._pending = {key: value for key, value in self._pending.items() if value[1] != target}
        now = time.monotonic()
        for entry in entries:
            win_id = entry["winId"]
            if win_id not in self._requested[target]:
                continue
            assets = self._asset_cache.get(win_id)
            if not assets:
                continue
            ttl = _VISIBLE_THUMBNAIL_TTL if entry.get("focused") or entry.get("_onCurrentTags") or current_tags & entry.get("tags", 0) else _BACKGROUND_THUMBNAIL_TTL
            thumbnail = include_thumbnails and not entry.get("minimized") and (
                assets.thumbnail_attempted_at == 0 or now - assets.thumbnail_attempted_at >= ttl or
                assets.thumbnail_geometry != entry.get("_geometry", (0, 0)))
            if thumbnail or not assets.icon_attempted:
                self._pending[win_id] = (generation, target, dict(entry), thumbnail, not assets.icon_attempted)
        self._dispatch_captures()

    def _dispatch_captures(self):
        for win_id in list(self._pending):
            if len(self._inflight) >= _CAPTURE_WORKERS:
                break
            if win_id in self._inflight:
                continue
            request = self._pending.pop(win_id)
            self._inflight[win_id] = request
            future = self._capture_pool.submit(self._capture_request, request)
            future.add_done_callback(lambda future, request=request: self._captureDone.emit((request, future)))

    def _capture_request(self, request):
        _, _, entry, thumbnail, icon = request
        result = {}
        if thumbnail:
            result["thumbnail"] = self._capture_asset("thumbnail", entry)
        if icon:
            result["icon"] = self._capture_asset("icon", entry)
        return result

    @Slot(object)
    def _finish_capture(self, payload):
        request, future = payload
        generation, target, entry, _, _ = request
        win_id = entry["winId"]
        self._inflight.pop(win_id, None)
        try:
            result = future.result()
        except Exception:
            result = {}
        current_generation = self._refresh_generation if target == "normal" else self._minimized_generation
        assets = self._asset_cache.get(win_id)
        valid = (not self._stopped and generation == current_generation and
                 win_id in self._requested[target] and assets and assets.wm_class == entry["wmClass"] and
                 assets.identity == entry.get("_identity"))
        if valid:
            if self._pending.get(win_id) == request:
                self._pending.pop(win_id, None)
            changes = {}
            old_uris = []
            for kind, uri in result.items():
                old_uris.append(assets.thumbnail_uri if kind == "thumbnail" else assets.icon_uri)
                changes["thumbnailUri" if kind == "thumbnail" else "iconUri"] = self._remember_asset(entry, kind, uri)
                if kind == "thumbnail":
                    assets.thumbnail_attempted_at = time.monotonic()
                else:
                    assets.icon_attempted = True
            self._apply_asset(generation, target, win_id, changes)
            for uri in old_uris:
                if uri and uri not in changes.values():
                    _delete_owned_uri(uri)
        else:
            for uri in result.values():
                _delete_owned_uri(uri)
        if not self._stopped:
            self._dispatch_captures()

    @staticmethod
    def _capture_asset(kind, entry):
        token = time.monotonic_ns()
        if kind == "thumbnail":
            return _capture_thumbnail_file_uri(entry["winId"], token)
        return _net_wm_icon_file_uri(
            entry["winId"], entry["wmClass"], token
        )

    def _remember_asset(self, entry, kind, uri):
        with self._asset_cache_lock:
            assets = self._asset_cache.get(entry["winId"])
            if assets is None or assets.wm_class != entry["wmClass"]:
                return uri
            if kind == "thumbnail":
                if uri:
                    assets.thumbnail_uri = uri
                    assets.thumbnail_geometry = entry.get(
                        "_geometry", (0, 0)
                    )
                elif not assets.thumbnail_uri:
                    assets.thumbnail_geometry = entry.get(
                        "_geometry", (0, 0)
                    )
                return assets.thumbnail_uri
            else:
                if uri:
                    assets.icon_uri = uri
                return assets.icon_uri

    @Slot(int, str, int, object)
    def _apply_asset(self, generation, target, win_id, changes):
        if target == "normal":
            if generation != self._refresh_generation:
                return
        else:
            if generation != self._minimized_generation:
                return
        collections = (
            (
                self._windows,
                self._windows_model,
                self.windowsChanged,
            ),
            (
                self._minimized_windows,
                self._minimized_windows_model,
                self.minimizedWindowsChanged,
            ),
        )
        for windows, model, changed_signal in collections:
            updated = False
            for entry in windows:
                if entry.get("winId") == win_id:
                    updated = any(entry.get(key) != value for key, value in changes.items())
                    entry.update(changes)
                    break
            if updated:
                model.update_item(win_id, changes)
                changed_signal.emit()

    @Slot(int)
    def _finish_minimized_refresh(self, _generation):
        if self._minimized_pending:
            self._minimized_pending = False
            self._start_minimized_refresh(self._minimized_generation)
            return
        self._minimized_running = False
        self.minimizedRefreshingChanged.emit()

    @Slot(int)
    def focusWindow(self, win_id: int):
        """Tell the WM to switch to the tag containing win_id and focus it."""
        self._remember_focused_window(win_id)
        threading.Thread(
            target=_sadewm_request,
            args=({"cmd": "focus_window", "win_id": win_id},),
            daemon=True,
            name="sadeshell-focus-window",
        ).start()

    @Slot()
    def stop(self):
        """Prevent further cache writes and remove this process's image cache."""
        if self._stopped:
            return
        self._stopped = True
        self._pending.clear()
        self._capture_pool.shutdown(wait=True, cancel_futures=True)
        with _CAPTURE_CONNECTIONS_LOCK:
            for connection in _CAPTURE_CONNECTIONS:
                connection.close()
            _CAPTURE_CONNECTIONS.clear()
        _cleanup_cache()
