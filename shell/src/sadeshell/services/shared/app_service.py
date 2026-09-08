"""AppService — .desktop entry discovery and launching."""

import os

from .icon_index import icons
import shutil
import subprocess
import configparser
import glob
import shlex
import threading

from PySide6.QtCore import (
    QObject, Property, Signal, Slot,
    QFileSystemWatcher, QTimer, QMetaObject, Qt, Q_ARG,
)


# True when sadeshell is running as a systemd user service unit.
# INVOCATION_ID is set by systemd for every service it starts.
_IS_SYSTEMD_UNIT = bool(os.environ.get("INVOCATION_ID"))
# Check once at import time whether systemd-run is available.
_SYSTEMD_RUN = shutil.which("systemd-run") if _IS_SYSTEMD_UNIT else None


def _make_scoped_cmd(argv: list[str]) -> list[str] | None:
    """If running under systemd, wrap argv in a transient user scope so
    the launched app is not a child of the sadeshell service and survives
    sadeshell restarts/stops.  Returns None if systemd-run is unavailable."""
    if not _SYSTEMD_RUN:
        return None
    return [_SYSTEMD_RUN, "--user", "--scope", "--", *argv]


def _desktop_bool(entry: dict, key: str) -> bool:
    return entry.get(key, "false").strip().lower() == "true"


def _desktop_list(value: str) -> set[str]:
    return {item for item in value.split(";") if item}


def _visible_on_current_desktop(entry: dict) -> bool:
    current = {
        desktop
        for desktop in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")
        if desktop
    }
    only_show_in = _desktop_list(entry.get("onlyshowin", ""))
    not_show_in = _desktop_list(entry.get("notshowin", ""))
    if only_show_in and not current.intersection(only_show_in):
        return False
    if current.intersection(not_show_in):
        return False
    return True


def _try_exec_available(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    if os.path.isabs(value):
        return os.path.isfile(value) and os.access(value, os.X_OK)
    return shutil.which(value) is not None


def _expand_exec(entry: dict) -> list[str]:
    """Expand Desktop Entry Exec field codes into a direct argv list."""
    raw = entry.get("exec", "")
    if not raw:
        return []
    try:
        tokens = shlex.split(raw, comments=False, posix=True)
    except ValueError:
        return []

    name = str(entry.get("name", ""))
    icon = str(entry.get("icon", ""))
    desktop_file = str(entry.get("desktopFile", ""))
    argv: list[str] = []

    for token in tokens:
        if token == "%i":
            if icon:
                argv.extend(["--icon", icon])
            continue

        expanded = []
        i = 0
        valid = True
        while i < len(token):
            if token[i] != "%":
                expanded.append(token[i])
                i += 1
                continue
            if i + 1 >= len(token):
                valid = False
                break
            code = token[i + 1]
            i += 2
            if code == "%":
                expanded.append("%")
            elif code == "c":
                expanded.append(name)
            elif code == "k":
                expanded.append(desktop_file)
            elif code in "fFuUdDnNvVm":
                # No file or URL was supplied by the launcher.
                continue
            else:
                # Unknown and embedded %i field codes make the entry invalid.
                valid = False
                break
        if not valid:
            return []
        value = "".join(expanded)
        if value:
            argv.append(value)

    return argv


def _terminal_prefix() -> list[str] | None:
    configured = os.environ.get("TERMINAL", "").strip()
    if configured:
        try:
            command = shlex.split(configured, comments=False, posix=True)
        except ValueError:
            command = []
    else:
        command = []
        for candidate in (
            "x-terminal-emulator", "kitty", "alacritty", "foot", "wezterm",
            "konsole", "gnome-terminal", "xfce4-terminal", "xterm",
        ):
            if path := shutil.which(candidate):
                command = [path]
                break
    if not command:
        return None

    terminal = os.path.basename(command[0])
    if terminal == "wezterm":
        return [*command, "start", "--"]
    if terminal in {"gnome-terminal", "kgx"}:
        return [*command, "--"]
    return [*command, "-e"]



def _resolve_icon(icon_name):
    path = icons.resolve(icon_name)
    return "file://" + path if path else ""


def _apps_dirs() -> list[str]:
    """Return the list of XDG applications directories that exist on disk."""
    dirs: list[str] = []
    xdg_data = os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share")
    for d in xdg_data.split(":"):
        app_dir = os.path.join(d, "applications")
        if os.path.isdir(app_dir):
            dirs.append(app_dir)

    home_apps = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "applications")
    # Ensure the user dir exists so we can watch it for new files even before
    # any .desktop files are installed there.
    os.makedirs(home_apps, exist_ok=True)
    if home_apps not in dirs:
        dirs.insert(0, home_apps)
    return dirs


def _parse_desktop_files():
    """Parse .desktop files from standard XDG directories."""
    dirs = _apps_dirs()

    apps = []
    seen = set()
    for app_dir in dirs:
        for f in glob.glob(os.path.join(app_dir, "*.desktop")):
            basename = os.path.basename(f)
            if basename in seen:
                continue
            seen.add(basename)

            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
            except (configparser.Error, OSError, UnicodeError):
                continue
            if not cp.has_section("Desktop Entry"):
                continue

            entry = dict(cp["Desktop Entry"])
            if entry.get("type", "Application") != "Application":
                continue
            if _desktop_bool(entry, "hidden") or _desktop_bool(entry, "nodisplay"):
                continue
            if not _visible_on_current_desktop(entry):
                continue
            if not _try_exec_available(entry.get("tryexec", "")):
                continue

            name = entry.get("name", basename)
            generic = entry.get("genericname", "")
            comment = entry.get("comment", "")
            icon = entry.get("icon", "")
            keywords = entry.get("keywords", "")
            exec_cmd = entry.get("exec", "")
            if not exec_cmd.strip():
                continue

            apps.append({
                "name": name,
                "genericName": generic,
                "comment": comment,
                "icon": icon,
                "iconPath": _resolve_icon(icon),
                "keywords": keywords,
                "exec": exec_cmd,
                "desktopFile": f,
                "terminal": _desktop_bool(entry, "terminal"),
            })

    apps.sort(key=lambda a: a["name"].lower())
    return apps


class AppService(QObject):
    appsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps: list = []
        self._scan_running = False
        self._scan_pending = False
        self._stopped = False

        # Watch XDG application dirs for new/removed .desktop files.
        self._watcher = QFileSystemWatcher(self)
        watched_dirs = _apps_dirs()
        self._watcher.addPaths(watched_dirs)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_dir_changed)

        # Debounce rapid successive filesystem events (e.g. a package manager
        # writing several .desktop files at once).
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.setInterval(500)
        self._rescan_timer.timeout.connect(self._start_rescan)

        # Initial load happens in the background so __init__ returns immediately
        # and does not block the Qt main thread during startup.
        self._start_rescan()

    @Slot(str)
    def _on_dir_changed(self, _path: str) -> None:
        """Called by QFileSystemWatcher when an applications/ dir changes."""
        # Restart the debounce timer so we batch rapid events.
        self._rescan_timer.start()

    @Slot()
    def refresh(self):
        self._start_rescan()

    @Slot()
    def _start_rescan(self) -> None:
        """Spawn a daemon thread to re-scan desktop files off the main thread."""
        if self._stopped:
            return
        if self._scan_running:
            self._scan_pending = True
            return
        self._scan_running = True
        threading.Thread(target=self._do_scan, daemon=True, name="sadeshell-app-scan").start()

    def _do_scan(self) -> None:
        """Worker: parse desktop files then schedule _set_apps on the main thread."""
        try:
            icons.invalidate()
            result = _parse_desktop_files()
        except Exception:
            result = self._apps.copy()
        QMetaObject.invokeMethod(
            self,
            "_set_apps",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG("QVariantList", result),
        )

    @Slot("QVariantList")
    def _set_apps(self, apps: list) -> None:
        """Main-thread slot: update the app list and notify QML."""
        self._scan_running = False
        if self._stopped:
            return
        if self._scan_pending:
            self._scan_pending = False
            self._start_rescan()
            return
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        directories = _apps_dirs()
        files = [p for directory in directories for p in glob.glob(os.path.join(directory, "*.desktop"))]
        paths = list(dict.fromkeys(directories + files + icons.directories))
        if paths:
            self._watcher.addPaths(paths)
        if self._apps != apps:
            self._apps = apps
            self.appsChanged.emit()

    def stop(self):
        self._stopped = True
        self._rescan_timer.stop()


    @Property("QVariantList", notify=appsChanged)
    def apps(self):
        return self._apps

    @Slot(str, result="QVariantList")
    def search(self, query):
        q = query.strip().lower()
        if not q:
            return self._apps
        return [a for a in self._apps
                if q in a["name"].lower()
                or q in a.get("genericName", "").lower()
                or q in a.get("comment", "").lower()
                or q in a.get("keywords", "").lower()]

    @Slot("QVariantList")
    def launchCommand(self, cmd):
        """Launch an arbitrary command list (used by QuickMenu shortcuts)."""
        if not cmd:
            return
        try:
            if _SYSTEMD_RUN:
                # Wrap in a transient scope so the child outlives sadeshell.
                launch = _make_scoped_cmd([str(arg) for arg in cmd])
                subprocess.Popen(
                    launch,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    @Slot("QVariant")
    def launch(self, entry):
        if not isinstance(entry, dict):
            return
        argv = _expand_exec(entry)
        if not argv:
            return
        if entry.get("terminal", False):
            terminal = _terminal_prefix()
            if terminal is None:
                return
            argv = [*terminal, *argv]
        try:
            command = _make_scoped_cmd(argv) or argv
            subprocess.Popen(
                command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
