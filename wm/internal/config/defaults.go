package config

import (
	"github.com/BurntSushi/xgb/xproto"
)

const (
	Version    = "0.9"
	HomeSubStr = "$HOME_PATH"
)

// Layout indices
const (
	LayoutTile  = 0
	LayoutFloat = 1
)

// Modifier keys
const (
	ModKey = xproto.ModMask4 // Super/Win
	AltKey = xproto.ModMask1 // Alt
)

const TerminalProgram = "wezterm"

// Appearance defaults
var (
	BorderPx       uint = 2
	GapPx          uint = 10
	Snap           uint = 32
	ColBorderNorm       = "#444444"
	ColBorderSel        = "#0099ff"
	MFact               = float32(0.5)
	NMaster             = 1
	ResizeHints         = true
	LockFullscreen      = true
	TopOffset      uint = 10
	BottomOffset   uint = 10
)

var SizeHintsWhitelist = []string{"mpv"}

// Titlebar colors – slightly lighter than the window background so the bar
// stands out. Override via [titlebar] in the TOML config.
var (
	TitlebarBgNorm   = "#24283b" // normal (unfocused) bar background
	TitlebarBgFocus  = "#2a2e45" // focused bar background
	TitlebarSep      = "#414868" // bottom separator line
	TitlebarText     = "#c0caf5" // title text
	TitlebarClose    = "#f7768e" // close button
	TitlebarAbove    = "#7aa2f7" // stay-on-top button
	TitlebarMinimize = "#9ece6a" // minimize button
)

var Tags = []string{"1", "2", "3", "4", "5", "6", "7", "8", "9"}

// Rule defines a window rule for auto-assigning tags/floating.
type Rule struct {
	Class      string
	Instance   string
	Title      string
	Tags       uint32
	IsFloating bool
	Monitor    int
}

var DefaultRules = []Rule{
	{Class: "Gimp", Tags: 0, IsFloating: true, Monitor: -1},
}

// Arg holds a polymorphic argument for key/button actions.
type Arg struct {
	I  int
	UI uint32
	F  float32
	V  any
}

// ActionFunc is the type for all WM action handlers.
type ActionFunc func(arg *Arg)

// Key defines a keybinding.
type Key struct {
	Mod    uint16
	KeyStr string // X keysym name (e.g. "p", "Return", "Tab")
	Action string // action name for dispatch
	Arg    Arg
}

// Button defines a mouse button binding.
type Button struct {
	Click  int
	Mask   uint16
	Button xproto.Button
	Action string
	Arg    Arg
}

// Click locations
const (
	ClkClientWin = iota
	ClkRootWin
)

// Layout defines a tiling layout.
type Layout struct {
	Symbol  string
	Arrange func(m any) // will be typed properly when wm package is available
}

// DefaultLayouts returns the built-in layouts. Arrange funcs are set later.
var DefaultLayouts = []Layout{
	{Symbol: "[]=", Arrange: nil}, // tile - set by wm package
	{Symbol: "><>", Arrange: nil}, // float
}

// DefaultKeys returns the compiled-in keybindings.
func DefaultKeys() []Key {
	mod := uint16(ModKey)
	alt := uint16(AltKey)
	shift := uint16(xproto.ModMaskShift)
	ctrl := uint16(xproto.ModMaskControl)

	keys := []Key{
		{Mod: mod, KeyStr: "p", Action: "spawn", Arg: Arg{V: []string{"sadeshell", "--open-launcher"}}},
		{Mod: mod, KeyStr: "period", Action: "spawn", Arg: Arg{V: []string{"sadeshell", "--open-emoji-picker"}}},
		{Mod: mod, KeyStr: "Return", Action: "spawn", Arg: Arg{V: []string{TerminalProgram}}},
		{Mod: mod, KeyStr: "Tab", Action: "focusstack", Arg: Arg{I: +1}},
		{Mod: mod | shift, KeyStr: "Tab", Action: "focusstack", Arg: Arg{I: -1}},
		{Mod: mod, KeyStr: "j", Action: "focusdown"},
		{Mod: mod, KeyStr: "k", Action: "focusup"},
		{Mod: mod, KeyStr: "h", Action: "focusleft"},
		{Mod: mod, KeyStr: "l", Action: "focusright"},
		{Mod: mod | shift, KeyStr: "j", Action: "swapdown"},
		{Mod: mod | shift, KeyStr: "k", Action: "swapup"},
		{Mod: mod | shift, KeyStr: "h", Action: "swapleft"},
		{Mod: mod | shift, KeyStr: "l", Action: "swapright"},
		{Mod: alt, KeyStr: "k", Action: "incnmaster", Arg: Arg{I: +1}},
		{Mod: alt, KeyStr: "j", Action: "incnmaster", Arg: Arg{I: -1}},
		{Mod: mod | ctrl, KeyStr: "h", Action: "setmfact", Arg: Arg{F: -0.05}},
		{Mod: mod | ctrl, KeyStr: "l", Action: "setmfact", Arg: Arg{F: +0.05}},
		{Mod: mod | shift, KeyStr: "Return", Action: "zoom"},
		{Mod: mod, KeyStr: "q", Action: "killclient"},
		{Mod: mod, KeyStr: "n", Action: "minimize"},
		{Mod: mod | ctrl, KeyStr: "n", Action: "restore"},
		{Mod: mod, KeyStr: "t", Action: "setlayout", Arg: Arg{I: LayoutTile}},
		{Mod: mod | shift, KeyStr: "f", Action: "setlayout", Arg: Arg{I: LayoutFloat}},
		{Mod: mod, KeyStr: "f", Action: "togglefullscr"},
		{Mod: mod, KeyStr: "m", Action: "togglemaximize"},
		{Mod: mod, KeyStr: "space", Action: "layoutnext"},
		{Mod: mod | shift, KeyStr: "space", Action: "layoutprev"},
		{Mod: mod | ctrl, KeyStr: "space", Action: "togglefloating"},
		{Mod: mod, KeyStr: "0", Action: "view", Arg: Arg{UI: ^uint32(0)}},
		{Mod: mod, KeyStr: "Escape", Action: "view"},
		{Mod: mod, KeyStr: "Left", Action: "viewprev"},
		{Mod: mod, KeyStr: "Right", Action: "viewnext"},
		{Mod: mod | shift, KeyStr: "0", Action: "tag", Arg: Arg{UI: ^uint32(0)}},
		{Mod: mod, KeyStr: "comma", Action: "focusmon", Arg: Arg{I: -1}},
		{Mod: mod | alt, KeyStr: "period", Action: "focusmon", Arg: Arg{I: +1}},
		{Mod: mod | shift, KeyStr: "comma", Action: "tagmon", Arg: Arg{I: -1}},
		{Mod: mod | alt | shift, KeyStr: "period", Action: "tagmon", Arg: Arg{I: +1}},
		{Mod: mod, KeyStr: "minus", Action: "setgaps", Arg: Arg{I: -1}},
		{Mod: mod, KeyStr: "equal", Action: "setgaps", Arg: Arg{I: +1}},
		{Mod: mod | shift, KeyStr: "equal", Action: "setgaps", Arg: Arg{I: 0}},
		{Mod: mod | shift, KeyStr: "r", Action: "reloadconfig"},
		{Mod: mod | shift, KeyStr: "q", Action: "quit"},
	}

	// TAGKEYS: for each tag 1-9, add view/toggleview/tag/toggletag bindings
	tagKeyNames := []string{"1", "2", "3", "4", "5", "6", "7", "8", "9"}
	for i, kn := range tagKeyNames {
		mask := uint32(1) << uint(i)
		keys = append(keys,
			Key{Mod: mod, KeyStr: kn, Action: "view", Arg: Arg{UI: mask}},
			Key{Mod: mod | ctrl, KeyStr: kn, Action: "toggleview", Arg: Arg{UI: mask}},
			Key{Mod: mod | shift, KeyStr: kn, Action: "tag", Arg: Arg{UI: mask}},
			Key{Mod: mod | ctrl | shift, KeyStr: kn, Action: "toggletag", Arg: Arg{UI: mask}},
		)
	}

	return keys
}

// DefaultButtons returns the compiled-in button bindings.
func DefaultButtons() []Button {
	mod := uint16(ModKey)
	return []Button{
		{Click: ClkClientWin, Mask: mod, Button: xproto.ButtonIndex1, Action: "movemouse"},
		{Click: ClkClientWin, Mask: mod, Button: xproto.ButtonIndex2, Action: "togglefloating"},
		{Click: ClkClientWin, Mask: mod, Button: xproto.ButtonIndex3, Action: "resizemouse"},
	}
}

// StartupCmds returns the commands to run on startup.
func StartupCmds() [][]string {
	return [][]string{
		{"sh", HomeSubStr + "/.config/sadewm/startup.sh"},
	}
}

// ModNameToMask maps modifier string names to X modifier masks.
var ModNameToMask = map[string]uint16{
	"super":   uint16(xproto.ModMask4),
	"alt":     uint16(xproto.ModMask1),
	"shift":   uint16(xproto.ModMaskShift),
	"control": uint16(xproto.ModMaskControl),
	"ctrl":    uint16(xproto.ModMaskControl),
}
