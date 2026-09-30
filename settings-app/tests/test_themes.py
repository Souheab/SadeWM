import subprocess

import pytest
import tomlkit

from sadesettings import appearance, config_store, main
from .test_responsiveness import wait_for


@pytest.fixture
def theme_environment(tmp_path, monkeypatch):
    root = tmp_path / "config"
    data = tmp_path / "data"
    schemes = data / "color-schemes"
    schemes.mkdir(parents=True)
    (schemes / "BreezeDark.colors").write_text(
        "[General]\nName=Breeze Dark\n[Colors:View]\nBackgroundNormal=27,30,32\n"
        "ForegroundNormal=239,240,241\n[Colors:Window]\nBackgroundNormal=42,46,50\n"
        "[ColorEffects:Disabled]\nColor=56,56,56\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system"))
    monkeypatch.setenv("SADE_THEME_DATA_DIRS", "")
    monkeypatch.setattr(appearance.shutil, "which", lambda name: None)
    return root, data


def test_dark_defaults_and_selection_round_trip():
    doc = tomlkit.parse('[other]\nvalue="keep"\n')
    assert config_store.get_appearance_values(doc) == {
        "gtk_theme": "Adwaita-dark", "qt_style": "Breeze",
        "qt_color_scheme": "BreezeDark", "prefer_dark": True,
    }
    values = dict(gtk_theme="Adwaita", qt_style="Fusion",
                  qt_color_scheme="Custom", prefer_dark=False)
    config_store.set_appearance_values(doc, values)
    restored = tomlkit.parse(tomlkit.dumps(doc))
    assert config_store.get_appearance_values(restored) == values
    assert restored["other"]["value"] == "keep"


def test_apply_replaces_old_palette_and_preserves_other_settings(theme_environment):
    root, _ = theme_environment
    root.mkdir()
    (root / "kdeglobals").write_text(
        "# keep comment\n[General]\nfont=Example,10\nColorScheme=Old\n"
        "[Colors:View]\nBackgroundNormal=255,255,255\nOldKey=remove\n"
        "[Colors:OldGroup]\nOldKey=remove\n[KDE]\nSingleClick=false\nwidgetStyle=Old\n"
    )
    gtk_dir = root / "gtk-3.0"
    gtk_dir.mkdir()
    (gtk_dir / "settings.ini").write_text(
        "# keep GTK comment\n[Settings]\ngtk-font-name=Example 11\ngtk-theme-name=Old\n"
    )
    values = config_store.APPEARANCE_DEFAULTS
    appearance.apply(values)
    kde = appearance._read_ini(root / "kdeglobals")
    assert kde["General"]["ColorScheme"] == "BreezeDark"
    assert kde["General"]["font"] == "Example,10"
    assert kde["KDE"]["widgetStyle"] == "Breeze"
    assert kde["KDE"]["SingleClick"] == "false"
    assert kde["Colors:View"]["BackgroundNormal"] == "27,30,32"
    assert "OldKey" not in kde["Colors:View"]
    assert "Colors:OldGroup" not in kde
    assert kde["ColorEffects:Disabled"]["Color"] == "56,56,56"
    assert "# keep comment" in (root / "kdeglobals").read_text()
    for version in ("gtk-3.0", "gtk-4.0"):
        gtk = appearance._read_ini(root / version / "settings.ini")
        assert gtk["Settings"]["gtk-theme-name"] == "Adwaita-dark"
        assert gtk["Settings"]["gtk-application-prefer-dark-theme"] == "true"
    assert gtk_dir.joinpath("settings.ini").read_text().startswith("# keep GTK comment")
    assert appearance._read_ini(gtk_dir / "settings.ini")["Settings"]["gtk-font-name"] == "Example 11"
    before = (root / "kdeglobals").read_text()
    appearance.apply(values)
    assert (root / "kdeglobals").read_text() == before


def test_invalid_or_missing_scheme_writes_nothing(theme_environment):
    root, _ = theme_environment
    for changes in ({"qt_color_scheme": "Missing"}, {"gtk_theme": "Bad\nsetting=true"}):
        with pytest.raises(ValueError):
            appearance.apply({**config_store.APPEARANCE_DEFAULTS, **changes})
        assert not root.exists()


def test_discovery_prefers_user_schemes(theme_environment, tmp_path):
    _, data = theme_environment
    (data / "themes" / "Custom GTK" / "gtk-3.0").mkdir(parents=True)
    other = tmp_path / "system"
    (other / "color-schemes").mkdir(parents=True)
    (other / "color-schemes" / "BreezeDark.colors").touch()
    assert "Custom GTK" in appearance.gtk_themes()
    assert appearance.qt_color_schemes()["BreezeDark"] == data / "color-schemes/BreezeDark.colors"


def test_gsettings_updates_and_reports_backend_errors(theme_environment, monkeypatch):
    calls = []
    monkeypatch.setattr(appearance.shutil, "which", lambda name: "/bin/gsettings")
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "list-keys":
            return subprocess.CompletedProcess(args, 0, "gtk-theme\ncolor-scheme\n", "")
        return subprocess.CompletedProcess(args, 0, "", "failed to commit changes to dconf")
    monkeypatch.setattr(appearance.subprocess, "run", run)
    warnings = appearance.apply(config_store.APPEARANCE_DEFAULTS)
    assert calls[1][-2:] == ["gtk-theme", '"Adwaita-dark"']
    assert calls[2][-2:] == ["color-scheme", '"prefer-dark"']
    assert "failed to commit" in warnings[0]
    calls.clear()
    appearance.apply({**config_store.APPEARANCE_DEFAULTS, "prefer_dark": False})
    assert calls[2][-1] == '"default"'


def test_appearance_ui_saves_selected_themes_without_wm(theme_environment, monkeypatch):
    root, data = theme_environment
    (data / "color-schemes/Custom.colors").write_text(
        "[Colors:View]\nBackgroundNormal=250,250,250\n"
    )
    monkeypatch.setattr(main.display, "query_outputs", lambda: [])
    monkeypatch.setattr(main.ipc, "send_reload", lambda: {"ok": False, "error": "not running"})
    window = main.SettingsWindow(root / "sade")
    monkeypatch.setattr(window, "_confirm_apply", lambda: True)
    try:
        assert window.gtk_theme.currentText() == "Adwaita-dark"
        assert window.qt_color_scheme.currentData() == "BreezeDark"
        assert window.prefer_dark.isChecked()
        window.gtk_theme.setCurrentText("Adwaita")
        window.qt_style.setCurrentText("Fusion")
        window.qt_color_scheme.setCurrentIndex(window.qt_color_scheme.findData("Custom"))
        window.prefer_dark.setChecked(False)
        window.apply()
        wait_for(lambda: not window._applying)
        saved = config_store.load_toml(root / "sade/settings.toml")
        assert saved["appearance"]["qt_color_scheme"] == "Custom"
        assert appearance._read_ini(root / "kdeglobals")["KDE"]["widgetStyle"] == "Fusion"
        assert "not running" in window.status.text()
        assert "Themes saved" in window.status.text()
    finally:
        window.close()


def test_headless_apply_uses_saved_preferences(theme_environment, monkeypatch):
    root, _ = theme_environment
    config = root / "sade"
    doc = tomlkit.document()
    config_store.set_appearance_values(doc, {"gtk_theme": "Adwaita", "prefer_dark": False})
    config_store.save_toml(config / "settings.toml", doc)
    def no_window(*args):
        pytest.fail("Headless appearance application must not create a QApplication")
    monkeypatch.setattr(main, "QApplication", no_window)
    assert main.main(["--config-dir", str(config), "--apply-appearance"]) == 0
    assert appearance._read_ini(root / "gtk-3.0/settings.ini")["Settings"]["gtk-theme-name"] == "Adwaita"


def test_headless_apply_reports_missing_scheme(theme_environment):
    root, data = theme_environment
    (data / "color-schemes/BreezeDark.colors").unlink()
    assert main.main(["--config-dir", str(root / "sade"), "--apply-appearance"]) == 1
    assert not root.exists()
