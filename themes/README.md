# sadewm Themes

Dark blue-purple themes matching the sadeshell status bar aesthetic.
All colors are sourced from `shell/src/components/shared/Theme.qml`.

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
