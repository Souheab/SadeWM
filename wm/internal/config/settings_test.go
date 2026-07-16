package config

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

const sampleXrandr = `Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
HDMI-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 510mm x 290mm
   1920x1080     60.00*+  59.94    50.00
   1280x720      60.00    59.94
DP-1 disconnected (normal left inverted right x axis y axis)
`

func TestFirstConnectedOutput(t *testing.T) {
	if got, want := FirstConnectedOutput(sampleXrandr), "HDMI-1"; got != want {
		t.Fatalf("FirstConnectedOutput = %q, want %q", got, want)
	}
}

func TestBuildXrandrArgsDefaultOutput(t *testing.T) {
	args, ok := BuildXrandrArgs(&DisplaySettings{
		Enabled:     true,
		Output:      "default",
		Resolution:  "1920x1080",
		RefreshRate: 60,
	}, sampleXrandr)
	if !ok {
		t.Fatal("BuildXrandrArgs returned ok=false")
	}
	want := []string{"--output", "HDMI-1", "--mode", "1920x1080", "--rate", "60"}
	if !reflect.DeepEqual(args, want) {
		t.Fatalf("args = %#v, want %#v", args, want)
	}
}

func TestBuildXrandrArgsDisabledOrIncomplete(t *testing.T) {
	cases := []*DisplaySettings{
		nil,
		{Enabled: false, Output: "default", Resolution: "1920x1080", RefreshRate: 60},
		{Enabled: true, Output: "default", RefreshRate: 60},
		{Enabled: true, Output: "default", Resolution: "1920x1080"},
	}
	for _, tc := range cases {
		if _, ok := BuildXrandrArgs(tc, sampleXrandr); ok {
			t.Fatalf("BuildXrandrArgs(%#v) returned ok=true", tc)
		}
	}
}

func TestLoadSettingsTOML(t *testing.T) {
	path := filepath.Join(t.TempDir(), "settings.toml")
	err := os.WriteFile(path, []byte(`[display]
enabled = true
output = "default"
resolution = "1280x720"
refresh_rate = 59.94

[power]
monitor_timeout_minutes = 10
sleep_timeout_minutes = 30
`), 0o644)
	if err != nil {
		t.Fatalf("write settings: %v", err)
	}

	cfg := LoadSettingsTOML(path)
	if cfg == nil || cfg.Display == nil {
		t.Fatal("expected display config")
	}
	if cfg.Display.Resolution != "1280x720" || cfg.Display.RefreshRate != 59.94 {
		t.Fatalf("unexpected display config: %+v", cfg.Display)
	}
	if cfg.Power == nil {
		t.Fatal("expected power config")
	}
	if cfg.Power.MonitorTimeoutMinutes != 10 || cfg.Power.SleepTimeoutMinutes != 30 {
		t.Fatalf("unexpected power config: %+v", cfg.Power)
	}
}
