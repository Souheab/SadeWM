package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestApplyTOMLBarAlwaysOnTop(t *testing.T) {
	old := BarAlwaysOnTop
	t.Cleanup(func() {
		BarAlwaysOnTop = old
	})

	enabled := true
	ApplyTOML(&TOMLConfig{
		Bar: &TOMLBar{
			AlwaysOnTop: &enabled,
		},
	})

	if !BarAlwaysOnTop {
		t.Fatal("expected bar always-on-top config to be applied")
	}
}

func TestApplyTOMLCenterFloating(t *testing.T) {
	old := CenterFloating
	t.Cleanup(func() {
		CenterFloating = old
	})

	disabled := false
	ApplyTOML(&TOMLConfig{
		Layout: &TOMLLayout{
			CenterFloating: &disabled,
		},
	})

	if CenterFloating {
		t.Fatal("expected center_floating config to be applied")
	}
}

func TestLoadTOMLBarAlwaysOnTop(t *testing.T) {
	path := filepath.Join(t.TempDir(), "wm.toml")
	err := os.WriteFile(path, []byte(`[bar]
always_on_top = true
`), 0o644)
	if err != nil {
		t.Fatalf("write config: %v", err)
	}

	cfg := LoadTOML(path)
	if cfg == nil || cfg.Bar == nil || cfg.Bar.AlwaysOnTop == nil {
		t.Fatal("expected bar config to load")
	}
	if !*cfg.Bar.AlwaysOnTop {
		t.Fatal("expected always_on_top = true")
	}
}

func TestLoadTOMLCenterFloating(t *testing.T) {
	path := filepath.Join(t.TempDir(), "wm.toml")
	err := os.WriteFile(path, []byte(`[layout]
center_floating = false
`), 0o644)
	if err != nil {
		t.Fatalf("write config: %v", err)
	}

	cfg := LoadTOML(path)
	if cfg == nil || cfg.Layout == nil || cfg.Layout.CenterFloating == nil {
		t.Fatal("expected center_floating config to load")
	}
	if *cfg.Layout.CenterFloating {
		t.Fatal("expected center_floating = false")
	}
}
