# sadewm Themes

Dark blue-purple themes matching the sadeshell status bar aesthetic.
All colors are sourced from `shell/src/sadeshell/components/shared/Theme.qml`.

## Application theme settings

Open **SadeSettings → Appearance** to choose a GTK theme, Qt widget style, and
Qt color scheme. The defaults are **Adwaita-dark** for GTK and **Breeze** with
the **Breeze Dark** color scheme for Qt. The dark-appearance checkbox also sets
the preference used by libadwaita when the GNOME GSettings schema is available.
Applications with their own appearance settings can override these preferences.

Apply saves the selection in `~/.config/sade/settings.toml` under `[appearance]`,
updates GTK 3/4 `settings.ini` and KDE `kdeglobals`, and preserves unrelated
settings. `XDG_CONFIG_HOME` is respected. GTK themes and Qt color schemes are
discovered in the user and system XDG data directories (plus `~/.themes` for
GTK). Install additional widget styles before entering their names.

The SADE NixOS session includes Breeze and KDE platform integration for Qt 5/6
and applies the saved selection, or the dark defaults, at login. Rebuild the
session and log out/in once after upgrading; restart applications after later
theme changes. SadeShell and SadeSettings retain their own SADE styling.

For manually started sessions, install Breeze (including `BreezeDark.colors`)
and KDE's Qt platform integration, then run these before starting the window
manager and shell:

```sh
export QT_QPA_PLATFORMTHEME=kde
sadesettings --apply-appearance
```

Remove conflicting `QT_STYLE_OVERRIDE` or `GTK_THEME` overrides if applications
ignore the selection. Existing XSettings daemons or sandbox portals can also
override per-user theme files. The theme assets below are optional SADE-specific
themes; they are separate from the standard Adwaita/Breeze defaults.

## Files

| File | Target |
|------|--------|
| `sadewm-qt5.qss` | Qt5 applications (PyQt5, PySide2) |
| `sadewm-qt6.qss` | Qt6 applications (PyQt6, PySide6) |
| `gtk2/gtkrc` | GTK2 applications |
| `gtk3/gtk.css` | GTK3 applications |
| `gtk4/gtk.css` | GTK4 applications (+ libadwaita) |

## Qt Usage

### qt5ct / qt6ct

1. Copy the `.qss` file to `~/.config/qt5ct/qss/` (or `qt6ct`).
2. Open qt5ct/qt6ct → Appearance → Style Sheet → select **sadewm-qt5** / **sadewm-qt6**.

### In application code

```python
# PySide6 / PyQt6
from pathlib import Path
qss = Path("themes/sadewm-qt6.qss").read_text()
app.setStyleSheet(qss)

# PySide2 / PyQt5
from pathlib import Path
qss = Path("themes/sadewm-qt5.qss").read_text()
app.setStyleSheet(qss)
```

## GTK Usage

### GTK2

```bash
mkdir -p ~/.themes/sadewm/gtk-2.0
cp themes/gtk2/gtkrc ~/.themes/sadewm/gtk-2.0/gtkrc
export GTK2_RC_FILES=~/.themes/sadewm/gtk-2.0/gtkrc
```

Requires the **murrine** GTK2 engine (`gtk-engine-murrine` or `gtk-murrine-engine`).

### GTK3

```bash
mkdir -p ~/.themes/sadewm/gtk-3.0
cp themes/gtk3/gtk.css ~/.themes/sadewm/gtk-3.0/gtk.css
export GTK_THEME=sadewm
# or: gsettings set org.gnome.desktop.interface gtk-theme 'sadewm'
```

### GTK4

```bash
# GTK4 reads user CSS from ~/.config/gtk-4.0/
mkdir -p ~/.config/gtk-4.0
cp themes/gtk4/gtk.css ~/.config/gtk-4.0/gtk.css
```

For libadwaita apps, this file is loaded automatically. For non-libadwaita GTK4 apps
you may also need `GTK_THEME=sadewm` with the theme installed to `~/.themes/`.

## Color palette

| Token | Hex | Role |
|-------|-----|------|
| `barBg` | `#1a1b26` | Deepest background |
| `containerBg` | `#292e42` | Surface / card |
| `buttonBg` | `#323851` | Control background |
| `menuHover` | `#3b4166` | Hover / selection |
| `menuBorder` | `#3d4166` | Borders / dividers |
| `dotEmpty` | `#414868` | Disabled elements |
| `dotOccupied` | `#666f99` | Subtle text / accents |
| `textColor` | `#c0caf5` | Primary text |
| `dotSelected` | `#7aa2f7` | Accent / focus ring |
| `dangerColor` | `#bf616a` | Destructive actions |
| `dotUrgent` | `#f7768e` | Error / urgent |
| `warningColor` | `#e0af68` | Warning |
