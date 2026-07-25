package wm

import (
	"fmt"
	"strings"

	"github.com/jezek/xgb/xproto"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/ipc"
)

func (wm *WM) ipcKeybinds() *ipc.Response {
	keybinds := make([]ipc.KeybindDTO, 0, len(wm.ActiveKeys))
	for _, key := range wm.ActiveKeys {
		keybinds = append(keybinds, ipc.KeybindDTO{
			Mod:         formatKeyMods(key.Mod),
			Key:         formatKeyName(key.KeyStr),
			Action:      key.Action,
			Description: describeKeybind(key),
		})
	}
	return &ipc.Response{OK: true, Keybinds: keybinds}
}

func formatKeyMods(mask uint16) []string {
	mods := []struct {
		mask uint16
		name string
	}{
		{uint16(config.ModKey), "Super"},
		{uint16(config.AltKey), "Alt"},
		{uint16(xproto.ModMaskControl), "Ctrl"},
		{uint16(xproto.ModMaskShift), "Shift"},
		{uint16(xproto.ModMask2), "Mod2"},
		{uint16(xproto.ModMask3), "Mod3"},
		{uint16(xproto.ModMask5), "Mod5"},
	}

	names := []string{}
	for _, mod := range mods {
		if mask&mod.mask != 0 {
			names = append(names, mod.name)
		}
	}
	return names
}

func formatKeyName(key string) string {
	switch key {
	case "Return":
		return "Enter"
	case "Escape":
		return "Esc"
	case "space":
		return "Space"
	case "period":
		return "."
	case "comma":
		return ","
	case "minus":
		return "-"
	case "equal":
		return "="
	default:
		if len(key) == 1 {
			return strings.ToUpper(key)
		}
		return key
	}
}

func describeKeybind(key config.Key) string {
	switch key.Action {
	case "spawn":
		return describeSpawn(key.Arg.V)
	case "shellcmd":
		if command, ok := key.Arg.V.(string); ok {
			switch command {
			case "open-window-picker":
				return "Switch windows"
			case "open-minimized-picker":
				return "Restore minimized window"
			}
		}
		return "Open shell control"
	case "focusstack":
		if key.Arg.I < 0 {
			return "Focus previous window"
		}
		return "Focus next window"
	case "focusup":
		return "Focus window above"
	case "focusdown":
		return "Focus window below"
	case "focusleft":
		return "Focus window left"
	case "focusright":
		return "Focus window right"
	case "swapup":
		return "Swap window up"
	case "swapdown":
		return "Swap window down"
	case "swapleft":
		return "Swap window left"
	case "swapright":
		return "Swap window right"
	case "incnmaster":
		if key.Arg.I > 0 {
			return "Increase master count"
		}
		return "Decrease master count"
	case "setmfact":
		if key.Arg.F > 0 {
			return "Increase master area"
		}
		return "Decrease master area"
	case "zoom":
		return "Zoom focused window"
	case "killclient":
		return "Close focused window"
	case "minimize":
		return "Minimize focused window"
	case "restore":
		return "Restore minimized window"
	case "setlayout":
		switch key.Arg.I {
		case config.LayoutTile:
			return "Use tile layout"
		case config.LayoutFloat:
			return "Use floating layout"
		default:
			return "Set layout"
		}
	case "togglefullscr":
		return "Toggle fullscreen"
	case "togglemaximize":
		return "Toggle maximize"
	case "layoutnext":
		return "Next layout"
	case "layoutprev":
		return "Previous layout"
	case "togglefloating":
		return "Toggle floating"
	case "view":
		return describeTagAction("View", key.Arg.UI)
	case "toggleview":
		return describeTagAction("Toggle view", key.Arg.UI)
	case "tag":
		return describeTagAction("Move window to", key.Arg.UI)
	case "toggletag":
		return describeTagAction("Toggle window on", key.Arg.UI)
	case "swapview":
		return "Return to previous tag"
	case "viewprev":
		return "View previous tag"
	case "viewnext":
		return "View next tag"
	case "focusmon":
		if key.Arg.I < 0 {
			return "Focus previous monitor"
		}
		return "Focus next monitor"
	case "tagmon":
		if key.Arg.I < 0 {
			return "Move window to previous monitor"
		}
		return "Move window to next monitor"
	case "setgaps":
		switch {
		case key.Arg.I > 0:
			return "Increase gaps"
		case key.Arg.I < 0:
			return "Decrease gaps"
		default:
			return "Reset gaps"
		}
	case "reloadconfig":
		return "Reload config"
	case "quit":
		return "Quit sadewm"
	default:
		return humanizeAction(key.Action)
	}
}

func describeSpawn(value any) string {
	argv, ok := value.([]string)
	if !ok || len(argv) == 0 {
		return "Run command"
	}
	joined := strings.Join(argv, " ")
	switch joined {
	case "sadeshell --open-launcher":
		return "Open application launcher"
	case "sadeshell --open-keybinds":
		return "Show keybinds"
	case "sadeshell --open-emoji-picker":
		return "Open emoji picker"
	case "sadeshell --open-window-picker":
		return "Switch windows"
	case "sadeshell --open-minimized-picker":
		return "Restore minimized window"
	case "sadeshell --confirm-exit":
		return "Open exit menu"
	case config.TerminalProgram:
		return "Open terminal"
	default:
		return fmt.Sprintf("Run %s", joined)
	}
}

func describeTagAction(prefix string, mask uint32) string {
	if mask == ^uint32(0) {
		return prefix + " all tags"
	}
	for i := range config.Tags {
		if mask == uint32(1)<<uint(i) {
			return fmt.Sprintf("%s tag %s", prefix, config.Tags[i])
		}
	}
	return prefix + " tags"
}

func humanizeAction(action string) string {
	if action == "" {
		return "Run action"
	}
	action = strings.ReplaceAll(action, "_", " ")
	action = strings.ReplaceAll(action, "-", " ")
	return strings.ToUpper(action[:1]) + action[1:]
}
