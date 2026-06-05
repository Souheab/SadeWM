package main

import (
	"path/filepath"
)

const defaultConfigSubdir = ".config/sade"

type configPaths struct {
	ConfigDir    string
	WMPath       string
	SettingsPath string
	StartupPath  string
	NoConfig     bool
}

func resolveConfigPaths(home, customDir, wmFile string, noConfig bool) configPaths {
	if noConfig {
		return configPaths{NoConfig: true}
	}

	configDir := customDir
	if configDir == "" && home != "" {
		configDir = filepath.Join(home, defaultConfigSubdir)
	}

	paths := configPaths{
		ConfigDir: configDir,
	}
	if configDir != "" {
		paths.WMPath = filepath.Join(configDir, "wm.toml")
		paths.SettingsPath = filepath.Join(configDir, "settings.toml")
		paths.StartupPath = filepath.Join(configDir, "startup.sh")
	}
	if wmFile != "" {
		paths.WMPath = wmFile
	}
	return paths
}
