just my hobby project building a basic X11 desktop environment

## Config

sadewm looks for user configuration in `~/.config/sade` by default:

- `wm.toml` overrides window manager settings such as appearance, colors, layout, rules, and keybindings.
- `settings.toml` stores display and X11 session power settings. The `[power]`
  `monitor_timeout_minutes` value controls when DPMS turns monitors off, while
  `sleep_timeout_minutes` controls when the system is suspended; `0` disables
  either timeout.
- `startup.sh` runs once when sadewm starts.

Use `sadewm -c /path/to/wm.toml` to load a specific window manager config, `sadewm -custom-config /path/to/dir` to use another config directory, or `sadewm -no-config` to skip user config and startup scripts. The default keybinding `Super+Shift+r` reloads the active config.

## Roadmap

### Improvements
- Improve the UI appearance

### Bugs/Issues to Fix
- Settings app scrolling on numerical selector causes numerical change
- Weird floating window and titlebar behavior
- Systray not working correctly for some apps (Qt apps)
