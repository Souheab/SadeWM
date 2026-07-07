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
