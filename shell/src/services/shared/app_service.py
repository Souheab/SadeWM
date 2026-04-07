"""AppService — .desktop entry discovery and launching."""

import os
import subprocess
import configparser
import glob

from PySide6.QtCore import QObject, Property, Signal, Slot


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


def _parse_desktop_files():
    """Parse .desktop files from standard XDG directories."""
    dirs = []
    xdg_data = os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share")
    for d in xdg_data.split(":"):
        app_dir = os.path.join(d, "applications")
        if os.path.isdir(app_dir):
            dirs.append(app_dir)

    home_apps = os.path.expanduser("~/.local/share/applications")
    if os.path.isdir(home_apps):
        dirs.insert(0, home_apps)

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
        self._apps = _parse_desktop_files()

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
            subprocess.Popen(
                exec_cmd,
                shell=True,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
