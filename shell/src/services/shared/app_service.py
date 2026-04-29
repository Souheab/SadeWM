"""AppService — .desktop entry discovery and launching."""

import os
import shutil
import subprocess
import configparser
import glob
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


def _make_scoped_cmd(exec_cmd: str) -> list[str] | None:
    """If running under systemd, wrap exec_cmd in a transient user scope so
    the launched app is not a child of the sadeshell service and survives
    sadeshell restarts/stops.  Returns None if systemd-run is unavailable."""
    if not _SYSTEMD_RUN:
        return None
    # systemd-run --user --scope -- sh -c <exec_cmd>
    return [_SYSTEMD_RUN, "--user", "--scope", "--", "sh", "-c", exec_cmd]


_ICON_THEME_PATHS = []

def _init_icon_paths():
    """Build list of icon theme directories to search."""
    if _ICON_THEME_PATHS:
        return

    candidates: list[str] = []

    # XDG standard paths
    xdg_data = os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share")
    for d in xdg_data.split(":"):
        for sub in ("icons", "pixmaps"):
            candidates.append(os.path.join(d, sub))

    # NixOS-specific: nix profile and current system
    for nix_base in (
        os.path.expanduser("~/.nix-profile/share"),
        "/run/current-system/sw/share",
        "/var/run/current-system/sw/share",
    ):
        for sub in ("icons", "pixmaps"):
            candidates.append(os.path.join(nix_base, sub))

    # Common fallbacks
    candidates += [
        "/usr/share/pixmaps",
        "/usr/local/share/pixmaps",
        os.path.expanduser("~/.local/share/icons"),
    ]

    seen: set[str] = set()
    for p in candidates:
        if os.path.isdir(p) and p not in seen:
            seen.add(p)
            _ICON_THEME_PATHS.append(p)

    # User icons take priority
    user = os.path.expanduser("~/.local/share/icons")
    if user in _ICON_THEME_PATHS and _ICON_THEME_PATHS[0] != user:
        _ICON_THEME_PATHS.remove(user)
        _ICON_THEME_PATHS.insert(0, user)


def _resolve_icon(icon_name):
    """Resolve an icon name to a file path, or return empty string."""
    if not icon_name:
        return ""
    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        return "file://" + icon_name

    _init_icon_paths()
    exts = (".svg", ".png", ".xpm")
    # Check if icon_name already has an extension
    if any(icon_name.endswith(e) for e in exts):
        for base in _ICON_THEME_PATHS:
            full = os.path.join(base, icon_name)
            if os.path.isfile(full):
                return "file://" + full
        return ""

    # Search common sizes in hicolor and other themes
    for base in _ICON_THEME_PATHS:
        # Check pixmaps/base directory directly
        for ext in exts:
            p = os.path.join(base, icon_name + ext)
            if os.path.isfile(p):
                return "file://" + p
        # Check theme subdirectories with extended size list
        for theme in ("hicolor", "Adwaita", "breeze", "Papirus", "Papirus-Dark",
                      "gnome", "oxygen", "elementary"):
            theme_dir = os.path.join(base, theme)
            if not os.path.isdir(theme_dir):
                continue
            for size in ("scalable", "512x512", "256x256", "1024x1024",
                         "128x128", "96x96", "64x64", "48x48",
                         "32x32", "24x24", "22x22", "16x16"):
                for cat in ("apps", "categories", "devices", "mimetypes", "status", "."):
                    for ext in exts:
                        p = os.path.join(theme_dir, size, cat, icon_name + ext)
                        if os.path.isfile(p):
                            return "file://" + p

    # Last resort: recursive glob across all icon directories.
    # Slower but catches icons in nix store paths or unusual theme layouts.
    for base in _ICON_THEME_PATHS:
        for ext in exts:
            try:
                matches = glob.glob(
                    os.path.join(base, "**", icon_name + ext), recursive=True
                )
            except Exception:
                continue
            if matches:
                # Prefer SVG; among rasters prefer larger files (higher resolution)
                matches.sort(
                    key=lambda p: (not p.endswith(".svg"), -os.path.getsize(p))
                )
                return "file://" + matches[0]

    return ""


def _apps_dirs() -> list[str]:
    """Return the list of XDG applications directories that exist on disk."""
    dirs: list[str] = []
    xdg_data = os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share")
    for d in xdg_data.split(":"):
        app_dir = os.path.join(d, "applications")
        if os.path.isdir(app_dir):
            dirs.append(app_dir)

    home_apps = os.path.expanduser("~/.local/share/applications")
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

            cp = configparser.ConfigParser(interpolation=None)
            cp.read(f, encoding="utf-8")
            if not cp.has_section("Desktop Entry"):
                continue

            entry = dict(cp["Desktop Entry"])
            if entry.get("type", "Application") != "Application":
                continue
            if entry.get("nodisplay", "false").lower() == "true":
                continue

            name = entry.get("name", basename)
            generic = entry.get("genericname", "")
            comment = entry.get("comment", "")
            icon = entry.get("icon", "")
            keywords = entry.get("keywords", "")
            exec_cmd = entry.get("exec", "")

            # Clean up Exec field — remove %u, %f, %U, %F etc.
            exec_cmd = exec_cmd.replace("%u", "").replace("%U", "")
            exec_cmd = exec_cmd.replace("%f", "").replace("%F", "")
            exec_cmd = exec_cmd.replace("%i", "").replace("%c", "").replace("%k", "")
            exec_cmd = exec_cmd.strip()

            apps.append({
                "name": name,
                "genericName": generic,
                "comment": comment,
                "icon": icon,
                "iconPath": _resolve_icon(icon),
                "keywords": keywords,
                "exec": exec_cmd,
                "desktopFile": f,
            })

    apps.sort(key=lambda a: a["name"].lower())
    return apps


class AppService(QObject):
    appsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps: list = []

        # Watch XDG application dirs for new/removed .desktop files.
        self._watcher = QFileSystemWatcher(self)
        watched_dirs = _apps_dirs()
        self._watcher.addPaths(watched_dirs)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

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
    def _start_rescan(self) -> None:
        """Spawn a daemon thread to re-scan desktop files off the main thread."""
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self) -> None:
        """Worker: parse desktop files then schedule _set_apps on the main thread."""
        result = _parse_desktop_files()
        QMetaObject.invokeMethod(
            self,
            "_set_apps",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG("QVariantList", result),
        )

    @Slot("QVariantList")
    def _set_apps(self, apps: list) -> None:
        """Main-thread slot: update the app list and notify QML."""
        self._apps = apps
        self.appsChanged.emit()

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
                # Wrap in a transient scope so the child outlives sadeshell
                import shlex
                exec_str = shlex.join(cmd)
                launch = [_SYSTEMD_RUN, "--user", "--scope", "--", "sh", "-c", exec_str]
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
        exec_cmd = entry.get("exec", "") if isinstance(entry, dict) else ""
        if not exec_cmd:
            return
        try:
            scoped = _make_scoped_cmd(exec_cmd)
            if scoped:
                subprocess.Popen(
                    scoped,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    exec_cmd,
                    shell=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass
