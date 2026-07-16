"""TOML config loading and saving for sadesettings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "sade"

WM_DEFAULTS: dict[str, dict[str, Any]] = {
    "appearance": {
        "borderpx": 2,
        "gappx": 10,
        "snap": 32,
    },
    "layout": {
        "mfact": 0.5,
        "nmaster": 1,
        "topoffset": 40,
        "bottomoffset": 0,
        "resizehints": True,
        "lockfullscreen": True,
        "center_floating": True,
    },
    "titlebar": {
        "bg": "#24283b",
        "bg_focused": "#2a2e45",
        "sep": "#414868",
        "text": "#c0caf5",
        "close": "#f7768e",
        "above": "#7aa2f7",
        "minimize": "#9ece6a",
    },
}

COLOR_DEFAULTS: dict[str, dict[str, str]] = {
    "norm": {"border": "#444444"},
    "sel": {"border": "#0099ff"},
}

DISPLAY_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "output": "default",
    "resolution": "",
    "refresh_rate": 60.0,
}

POWER_DEFAULTS: dict[str, int] = {
    "monitor_timeout_minutes": 0,
    "sleep_timeout_minutes": 0,
}


def config_paths(config_dir: Path) -> tuple[Path, Path]:
    return config_dir / "wm.toml", config_dir / "settings.toml"


def load_toml(path: Path):
    if path.exists():
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    return tomlkit.document()


def save_toml(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def ensure_table(parent, key: str):
    value = parent.get(key)
    if value is None:
        value = tomlkit.table()
        parent[key] = value
    return value


def ensure_wm_defaults(doc) -> None:
    for section, values in WM_DEFAULTS.items():
        table = ensure_table(doc, section)
        for key, value in values.items():
            table.setdefault(key, value)

    colors = ensure_table(doc, "colors")
    for section, values in COLOR_DEFAULTS.items():
        table = ensure_table(colors, section)
        for key, value in values.items():
            table.setdefault(key, value)


def ensure_display_defaults(doc) -> None:
    display = ensure_table(doc, "display")
    for key, value in DISPLAY_DEFAULTS.items():
        display.setdefault(key, value)


def ensure_power_defaults(doc) -> None:
    power = ensure_table(doc, "power")
    for key, value in POWER_DEFAULTS.items():
        power.setdefault(key, value)


def get_wm_values(doc) -> dict[str, Any]:
    ensure_wm_defaults(doc)
    colors = doc["colors"]
    values: dict[str, Any] = {}
    for section, defaults in WM_DEFAULTS.items():
        for key in defaults:
            values[f"{section}.{key}"] = doc[section][key]
    values["colors.norm.border"] = colors["norm"]["border"]
    values["colors.sel.border"] = colors["sel"]["border"]
    return values


def set_wm_values(doc, values: dict[str, Any]) -> None:
    ensure_wm_defaults(doc)
    for dotted, value in values.items():
        parts = dotted.split(".")
        table = doc
        for part in parts[:-1]:
            table = ensure_table(table, part)
        table[parts[-1]] = value


def get_display_values(doc) -> dict[str, Any]:
    ensure_display_defaults(doc)
    display = doc["display"]
    return {key: display[key] for key in DISPLAY_DEFAULTS}


def set_display_values(doc, values: dict[str, Any]) -> None:
    ensure_display_defaults(doc)
    display = doc["display"]
    for key in DISPLAY_DEFAULTS:
        if key in values:
            display[key] = values[key]


def get_power_values(doc) -> dict[str, int]:
    ensure_power_defaults(doc)
    power = doc["power"]
    return {key: int(power[key]) for key in POWER_DEFAULTS}


def set_power_values(doc, values: dict[str, int]) -> None:
    ensure_power_defaults(doc)
    power = doc["power"]
    for key in POWER_DEFAULTS:
        if key in values:
            power[key] = int(values[key])
