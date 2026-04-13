package config

import (
	"fmt"
	"os"
	"strings"

	"github.com/BurntSushi/toml"
	"github.com/BurntSushi/xgb/xproto"
)

// TOMLConfig mirrors the TOML file structure.
type TOMLConfig struct {
	Appearance *TOMLAppearance `toml:"appearance"`
	Colors     *TOMLColors     `toml:"colors"`
	Titlebar   *TOMLTitlebar   `toml:"titlebar"`
	Layout     *TOMLLayout     `toml:"layout"`
	Rules      []TOMLRule      `toml:"rules"`
	Keys       []TOMLKey       `toml:"keys"`
	TagKeys    []TOMLTagKey    `toml:"tagkeys"`
}

// TOMLTitlebar configures the floating-window titlebar colours.
type TOMLTitlebar struct {
	BgNorm   string `toml:"bg"`
	BgFocus  string `toml:"bg_focused"`
	Sep      string `toml:"sep"`
	Text     string `toml:"text"`
	Close    string `toml:"close"`
	Above    string `toml:"above"`
	Minimize string `toml:"minimize"`
}

type TOMLAppearance struct {
	BorderPx *int `toml:"borderpx"`
	GapPx    *int `toml:"gappx"`
	Snap     *int `toml:"snap"`
}

type TOMLColors struct {
	Norm *TOMLBorderColor `toml:"norm"`
	Sel  *TOMLBorderColor `toml:"sel"`
}

type TOMLBorderColor struct {
	Border string `toml:"border"`
}

type TOMLLayout struct {
	MFact          *float64 `toml:"mfact"`
	NMaster        *int     `toml:"nmaster"`
	TopOffset      *int     `toml:"topoffset"`
	BottomOffset   *int     `toml:"bottomoffset"`
	ResizeHints    *bool    `toml:"resizehints"`
	LockFullscreen *bool    `toml:"lockfullscreen"`
}

type TOMLRule struct {
	Class      string `toml:"class"`
	Instance   string `toml:"instance"`
	Title      string `toml:"title"`
	TagsMask   int    `toml:"tags_mask"`
	IsFloating bool   `toml:"isfloating"`
	Monitor    int    `toml:"monitor"`
}

type TOMLKey struct {
	Mod      []string `toml:"mod"`
	Key      string   `toml:"key"`
	Action   string   `toml:"action"`
	Cmd      string   `toml:"cmd"`
	Layout   string   `toml:"layout"`
	ArgInt   *int     `toml:"arg_int"`
	ArgUint  *int     `toml:"arg_uint"`
	ArgFloat *float64 `toml:"arg_float"`
}

type TOMLTagKey struct {
	Key string `toml:"key"`
	Tag int    `toml:"tag"`
}

// LoadTOML reads a TOML config file and returns the parsed structure.
// Returns nil if the file doesn't exist or can't be parsed.
func LoadTOML(path string) *TOMLConfig {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}

	var cfg TOMLConfig
	if err := toml.Unmarshal(data, &cfg); err != nil {
		fmt.Fprintf(os.Stderr, "sadewm: error parsing config %s: %v\n", path, err)
		return nil
	}

	return &cfg
}

// ApplyTOML applies TOML overrides to the global config defaults.
func ApplyTOML(tc *TOMLConfig) {
	if tc == nil {
		return
	}

	if tc.Appearance != nil {
		if tc.Appearance.BorderPx != nil {
			BorderPx = uint(*tc.Appearance.BorderPx)
		}
		if tc.Appearance.GapPx != nil {
			GapPx = uint(*tc.Appearance.GapPx)
		}
		if tc.Appearance.Snap != nil {
			Snap = uint(*tc.Appearance.Snap)
		}
	}

	if tc.Colors != nil {
		if tc.Colors.Norm != nil && tc.Colors.Norm.Border != "" {
			ColBorderNorm = tc.Colors.Norm.Border
		}
		if tc.Colors.Sel != nil && tc.Colors.Sel.Border != "" {
			ColBorderSel = tc.Colors.Sel.Border
		}
	}

	if tb := tc.Titlebar; tb != nil {
		if tb.BgNorm != "" {
			TitlebarBgNorm = tb.BgNorm
		}
		if tb.BgFocus != "" {
			TitlebarBgFocus = tb.BgFocus
		}
		if tb.Sep != "" {
			TitlebarSep = tb.Sep
		}
		if tb.Text != "" {
			TitlebarText = tb.Text
		}
		if tb.Close != "" {
			TitlebarClose = tb.Close
		}
		if tb.Above != "" {
			TitlebarAbove = tb.Above
		}
		if tb.Minimize != "" {
			TitlebarMinimize = tb.Minimize
		}
	}

	if tc.Layout != nil {
		if tc.Layout.MFact != nil {
			MFact = float32(*tc.Layout.MFact)
		}
		if tc.Layout.NMaster != nil {
			NMaster = *tc.Layout.NMaster
		}
		if tc.Layout.TopOffset != nil {
			TopOffset = uint(*tc.Layout.TopOffset)
		}
		if tc.Layout.BottomOffset != nil {
			BottomOffset = uint(*tc.Layout.BottomOffset)
		}
		if tc.Layout.ResizeHints != nil {
			ResizeHints = *tc.Layout.ResizeHints
		}
		if tc.Layout.LockFullscreen != nil {
			LockFullscreen = *tc.Layout.LockFullscreen
		}
	}
}

// ApplyTOMLRules returns Rule slice from TOML config, or defaults if absent.
func ApplyTOMLRules(tc *TOMLConfig) []Rule {
	if tc == nil || len(tc.Rules) == 0 {
		return DefaultRules
	}

	rules := make([]Rule, len(tc.Rules))
	for i, tr := range tc.Rules {
		rules[i] = Rule{
			Class:      tr.Class,
			Instance:   tr.Instance,
			Title:      tr.Title,
			Tags:       uint32(tr.TagsMask),
			IsFloating: tr.IsFloating,
			Monitor:    tr.Monitor,
		}
	}
	return rules
}

// MergeKeys merges TOML keybindings with compiled-in defaults.
// mod+keysym deduplication: TOML overrides compiled-in.
// action="none" removes the binding.
func MergeKeys(tc *TOMLConfig, defaults []Key) []Key {
	if tc == nil || (len(tc.Keys) == 0 && len(tc.TagKeys) == 0) {
		return defaults
	}

	// Copy defaults
	keys := make([]Key, len(defaults))
	copy(keys, defaults)

	// Merge [[keys]]
	for _, fk := range tc.Keys {
		mod := resolveMods(fk.Mod)

		// action = "none" → unbind
		if fk.Action == "none" {
			keys = removeKey(keys, mod, fk.Key)
			continue
		}

		arg := Arg{}
		if fk.Cmd != "" {
			arg.V = []string{"/bin/sh", "-c", fk.Cmd}
		} else if fk.Layout != "" {
			switch fk.Layout {
			case "tile":
				arg.I = LayoutTile
			case "float":
				arg.I = LayoutFloat
			}
		} else if fk.ArgFloat != nil {
			arg.F = float32(*fk.ArgFloat)
		} else if fk.ArgUint != nil {
			arg.UI = uint32(*fk.ArgUint)
		} else if fk.ArgInt != nil {
			arg.I = *fk.ArgInt
		}

		keys = upsertKey(keys, Key{
			Mod:    mod,
			KeyStr: fk.Key,
			Action: fk.Action,
			Arg:    arg,
		})
	}

	// Merge [[tagkeys]]
	mod := uint16(ModKey)
	shift := uint16(xproto.ModMaskShift)
	ctrl := uint16(xproto.ModMaskControl)

	for _, tk := range tc.TagKeys {
		if tk.Tag < 0 || tk.Tag > 8 {
			continue
		}
		mask := uint32(1) << uint(tk.Tag)

		type tkMap struct {
			mod    uint16
			action string
		}
		maps := []tkMap{
			{mod, "view"},
			{mod | ctrl, "toggleview"},
			{mod | shift, "tag"},
			{mod | ctrl | shift, "toggletag"},
		}

		for _, m := range maps {
			keys = upsertKey(keys, Key{
				Mod:    m.mod,
				KeyStr: tk.Key,
				Action: m.action,
				Arg:    Arg{UI: mask},
			})
		}
	}

	return keys
}

func resolveMods(mods []string) uint16 {
	var mask uint16
	for _, m := range mods {
		if v, ok := ModNameToMask[strings.ToLower(m)]; ok {
			mask |= v
		}
	}
	return mask
}

func removeKey(keys []Key, mod uint16, keyStr string) []Key {
	for i := 0; i < len(keys); i++ {
		if keys[i].Mod == mod && keys[i].KeyStr == keyStr {
			keys = append(keys[:i], keys[i+1:]...)
			return keys
		}
	}
	return keys
}

func upsertKey(keys []Key, k Key) []Key {
	for i := range keys {
		if keys[i].Mod == k.Mod && keys[i].KeyStr == k.KeyStr {
			keys[i] = k
			return keys
		}
	}
	return append(keys, k)
}

// PrintConfig prints the active config to stdout (for -t flag).
func PrintConfig(rules []Rule, keys []Key) {
	fmt.Println("[appearance]")
	fmt.Printf("  borderpx      = %d\n", BorderPx)
	fmt.Printf("  gappx         = %d\n", GapPx)
	fmt.Printf("  snap          = %d\n", Snap)

	fmt.Println("[colors.norm]")
	fmt.Printf("  border        = \"%s\"\n", ColBorderNorm)
	fmt.Println("[colors.sel]")
	fmt.Printf("  border        = \"%s\"\n", ColBorderSel)

	fmt.Println("[layout]")
	fmt.Printf("  mfact         = %.2f\n", MFact)
	fmt.Printf("  nmaster       = %d\n", NMaster)
	fmt.Printf("  topoffset     = %d\n", TopOffset)
	fmt.Printf("  bottomoffset  = %d\n", BottomOffset)
	fmt.Printf("  resizehints   = %v\n", ResizeHints)
	fmt.Printf("  lockfullscreen= %v\n", LockFullscreen)

	fmt.Printf("[[rules]]  (%d active)\n", len(rules))
	for _, r := range rules {
		fmt.Printf("  class=%-12s instance=%-12s title=%-12s tags=0x%x float=%v mon=%d\n",
			r.Class, r.Instance, r.Title, r.Tags, r.IsFloating, r.Monitor)
	}

	fmt.Printf("[[keys]]  (%d active)\n", len(keys))
	for _, k := range keys {
		fmt.Printf("  mod=0x%04x key=%-12s action=%s\n", k.Mod, k.KeyStr, k.Action)
	}
}
