package main

import (
	"path/filepath"
	"testing"
)

func TestResolveConfigPathsDefault(t *testing.T) {
	paths := resolveConfigPaths("/home/alice", "", "", false)

	wantDir := filepath.Join("/home/alice", ".config/sade")
	if paths.ConfigDir != wantDir {
		t.Fatalf("ConfigDir = %q, want %q", paths.ConfigDir, wantDir)
	}
	if paths.WMPath != filepath.Join(wantDir, "wm.toml") {
		t.Fatalf("WMPath = %q", paths.WMPath)
	}
	if paths.SettingsPath != filepath.Join(wantDir, "settings.toml") {
		t.Fatalf("SettingsPath = %q", paths.SettingsPath)
	}
	if paths.StartupPath != filepath.Join(wantDir, "startup.sh") {
		t.Fatalf("StartupPath = %q", paths.StartupPath)
	}
}

func TestResolveConfigPathsCustomDir(t *testing.T) {
	paths := resolveConfigPaths("/home/alice", "/tmp/sade-test", "", false)

	if paths.ConfigDir != "/tmp/sade-test" {
		t.Fatalf("ConfigDir = %q", paths.ConfigDir)
	}
	if paths.WMPath != filepath.Join("/tmp/sade-test", "wm.toml") {
		t.Fatalf("WMPath = %q", paths.WMPath)
	}
}

func TestResolveConfigPathsExplicitWMFile(t *testing.T) {
	paths := resolveConfigPaths("/home/alice", "/tmp/sade-test", "/tmp/wm.toml", false)

	if paths.ConfigDir != "/tmp/sade-test" {
		t.Fatalf("ConfigDir = %q", paths.ConfigDir)
	}
	if paths.WMPath != "/tmp/wm.toml" {
		t.Fatalf("WMPath = %q", paths.WMPath)
	}
	if paths.SettingsPath != filepath.Join("/tmp/sade-test", "settings.toml") {
		t.Fatalf("SettingsPath = %q", paths.SettingsPath)
	}
}

func TestResolveConfigPathsNoConfig(t *testing.T) {
	paths := resolveConfigPaths("/home/alice", "/tmp/sade-test", "/tmp/wm.toml", true)

	if !paths.NoConfig {
		t.Fatal("NoConfig was false")
	}
	if paths.ConfigDir != "" || paths.WMPath != "" || paths.SettingsPath != "" || paths.StartupPath != "" {
		t.Fatalf("expected empty paths with no config: %+v", paths)
	}
}
