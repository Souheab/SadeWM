"""Discover and apply GTK themes and KDE/Qt application styles and palettes."""

from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from . import config_store


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def data_dirs() -> list[Path]:
    user = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    # Packaged defaults follow user/system themes so custom installations win.
    bundled = os.environ.get("SADE_THEME_DATA_DIRS", "")
    return [user, *(Path(p) for p in (system + ":" + bundled).split(":") if p)]


def gtk_themes() -> list[str]:
    names = {"Adwaita", "Adwaita-dark"}
    for root in [Path.home() / ".themes", *(p / "themes" for p in data_dirs())]:
        if root.is_dir():
            for path in root.iterdir():
                if any((path / version).is_dir() for version in ("gtk-3.0", "gtk-4.0")):
                    names.add(path.name)
    return sorted(names, key=str.casefold)


def qt_color_schemes() -> dict[str, Path]:
    schemes = {}
    for root in data_dirs():
        for path in sorted((root / "color-schemes").glob("*.colors")):
            schemes.setdefault(path.stem, path)
    return schemes


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    if path.exists():
        parser.read_string(path.read_text(encoding="utf-8"))
    return parser


def _update_ini(path: Path, updates: dict[str, dict[str, str]], *, replace_colors=False) -> str:
    """Keep unrelated keys and comments, replacing complete KDE color groups."""
    pending = {section: dict(values) for section, values in updates.items()}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    result = []
    section = None
    skip = False

    def append_missing():
        if skip:
            return
        for key, value in pending.pop(section, {}).items():
            result.append(f"{key}={value}")

    for line in lines:
        match = re.fullmatch(r"\s*\[(.+)\]\s*", line)
        if match:
            append_missing()
            section = match.group(1)
            skip = replace_colors and section.startswith(("Colors:", "ColorEffects:"))
            if not skip:
                result.append(line)
            continue
        if skip:
            continue
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in updates.get(section, {}) and not line.lstrip().startswith(("#", ";")):
            if key in pending.get(section, {}):
                result.append(f"{key}={pending[section].pop(key)}")
        else:
            result.append(line)
    append_missing()
    for section, values in pending.items():
        if result and result[-1]:
            result.append("")
        result.append(f"[{section}]")
        result.extend(f"{key}={value}" for key, value in values.items())
    return "\n".join(result) + "\n"


def prepare(values: dict) -> dict[Path, str]:
    """Validate and render all files before writing any application settings."""
    for key in ("gtk_theme", "qt_style", "qt_color_scheme"):
        value = values[key]
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0"):
            raise ValueError(f"Invalid {key.replace('_', ' ')}")
    scheme_name = values["qt_color_scheme"]
    scheme_path = qt_color_schemes().get(scheme_name)
    if scheme_path is None:
        raise ValueError(f"Qt color scheme {scheme_name!r} is not installed; install Breeze or choose an installed scheme")
    scheme = _read_ini(scheme_path)
    if not scheme.has_section("Colors:View"):
        raise ValueError(f"Invalid Qt color scheme: {scheme_path}")
    kde = {
        "General": {"ColorScheme": scheme_name},
        "KDE": {"widgetStyle": values["qt_style"]},
    }
    for section in scheme.sections():
        if section.startswith(("Colors:", "ColorEffects:")):
            kde[section] = dict(scheme[section])
    gtk = {"Settings": {
        "gtk-theme-name": values["gtk_theme"],
        "gtk-application-prefer-dark-theme": str(bool(values["prefer_dark"])).lower(),
    }}
    root = config_home()
    files = {root / "kdeglobals": _update_ini(root / "kdeglobals", kde, replace_colors=True)}
    for version in ("gtk-3.0", "gtk-4.0"):
        path = root / version / "settings.ini"
        files[path] = _update_ini(path, gtk)
    return files


def apply(values: dict) -> list[str]:
    for path, content in prepare(values).items():
        config_store.save_text(path, content)
    # Also publish the preference used by libadwaita and GNOME settings bridges.
    # Files above remain useful on minimal sessions without GSettings schemas.
    warnings = []
    executable = shutil.which("gsettings")
    if not executable:
        return ["GSettings unavailable; libadwaita dark preference was not updated"]
    try:
        schema = "org.gnome.desktop.interface"
        keys = subprocess.run([executable, "list-keys", schema], check=True,
                              capture_output=True, text=True, timeout=5).stdout.splitlines()
        preferences = {
            "gtk-theme": values["gtk_theme"],
            "color-scheme": "prefer-dark" if values["prefer_dark"] else "default",
        }
        for key, value in preferences.items():
            if key in keys:
                result = subprocess.run([executable, "set", schema, key, json.dumps(value)],
                                        check=True, capture_output=True, text=True, timeout=5)
                # dconf can report a failed write on stderr with a zero exit code.
                if result.stderr.strip():
                    warnings.append(result.stderr.strip())
            else:
                warnings.append(f"GSettings {key} unavailable")
    except (OSError, subprocess.SubprocessError) as exc:
        warnings.append(f"Could not update GSettings: {exc}")
    return warnings
