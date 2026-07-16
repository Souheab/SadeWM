import pytest

tomlkit = pytest.importorskip("tomlkit")

from sadesettings import config_store


def test_wm_defaults_are_created():
    doc = tomlkit.document()

    config_store.ensure_wm_defaults(doc)

    assert doc["appearance"]["gappx"] == 10
    assert doc["layout"]["mfact"] == 0.5
    assert doc["layout"]["topoffset"] == 40
    assert doc["layout"]["bottomoffset"] == 0
    assert doc["layout"]["center_floating"] is True
    assert doc["colors"]["sel"]["border"] == "#0099ff"


def test_wm_write_preserves_unknown_sections_and_arrays():
    doc = tomlkit.parse(
        """
[custom]
value = "keep"

[[keys]]
key = "x"
action = "spawn"
"""
    )

    config_store.set_wm_values(doc, {"appearance.gappx": 22})
    rendered = tomlkit.dumps(doc)

    assert doc["custom"]["value"] == "keep"
    assert doc["keys"][0]["key"] == "x"
    assert "gappx = 22" in rendered


def test_display_values_update_preserves_other_settings():
    doc = tomlkit.parse(
        """
[other]
name = "keep"
"""
    )

    config_store.set_display_values(
        doc,
        {
            "enabled": True,
            "output": "HDMI-1",
            "resolution": "1920x1080",
            "refresh_rate": 60.0,
        },
    )

    assert doc["other"]["name"] == "keep"
    assert doc["display"]["enabled"] is True
    assert doc["display"]["output"] == "HDMI-1"


def test_power_defaults_disable_idle_actions():
    doc = tomlkit.document()

    config_store.ensure_power_defaults(doc)

    assert doc["power"]["monitor_timeout_minutes"] == 0
    assert doc["power"]["sleep_timeout_minutes"] == 0


def test_power_values_update_preserves_other_settings():
    doc = tomlkit.parse(
        """
[other]
name = "keep"
"""
    )

    config_store.set_power_values(
        doc,
        {
            "monitor_timeout_minutes": 10,
            "sleep_timeout_minutes": 30,
        },
    )

    assert doc["other"]["name"] == "keep"
    assert config_store.get_power_values(doc) == {
        "monitor_timeout_minutes": 10,
        "sleep_timeout_minutes": 30,
    }
