package config

import (
	"os"
	"strconv"
	"strings"

	"github.com/BurntSushi/toml"
)

type SettingsConfig struct {
	Display *DisplaySettings `toml:"display"`
	Power   *PowerSettings   `toml:"power"`
}

type DisplaySettings struct {
	Enabled     bool    `toml:"enabled"`
	Output      string  `toml:"output"`
	Resolution  string  `toml:"resolution"`
	RefreshRate float64 `toml:"refresh_rate"`
}

type PowerSettings struct {
	MonitorTimeoutMinutes int `toml:"monitor_timeout_minutes"`
	SleepTimeoutMinutes   int `toml:"sleep_timeout_minutes"`
}

func LoadSettingsTOML(path string) *SettingsConfig {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}

	var cfg SettingsConfig
	if err := toml.Unmarshal(data, &cfg); err != nil {
		return nil
	}
	return &cfg
}

func BuildXrandrArgs(display *DisplaySettings, queryOutput string) ([]string, bool) {
	if display == nil || !display.Enabled || display.Resolution == "" || display.RefreshRate <= 0 {
		return nil, false
	}

	output := strings.TrimSpace(display.Output)
	if output == "" || output == "default" {
		output = FirstConnectedOutput(queryOutput)
	}
	if output == "" {
		return nil, false
	}

	return []string{
		"--output", output,
		"--mode", display.Resolution,
		"--rate", formatRefreshRate(display.RefreshRate),
	}, true
}

func FirstConnectedOutput(queryOutput string) string {
	for _, line := range strings.Split(queryOutput, "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && fields[1] == "connected" {
			return fields[0]
		}
	}
	return ""
}

func formatRefreshRate(rate float64) string {
	s := strconv.FormatFloat(rate, 'f', 2, 64)
	s = strings.TrimRight(s, "0")
	s = strings.TrimRight(s, ".")
	return s
}
