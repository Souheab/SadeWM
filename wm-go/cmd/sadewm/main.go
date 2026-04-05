package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/sadewm/sadewm/wm-go/internal/config"
	"github.com/sadewm/sadewm/wm-go/internal/ipc"
	"github.com/sadewm/sadewm/wm-go/internal/util"
	"github.com/sadewm/sadewm/wm-go/internal/wm"
)

func main() {
	defer util.CrashHandler()

	version := flag.Bool("v", false, "print version and exit")
	debugFlag := flag.Bool("d", false, "enable debug logging")
	topBar := flag.Uint("t", 0, "top offset for status bar (pixels)")
	configPath := flag.String("c", "", "path to TOML config file")
	flag.Parse()

	if *version {
		fmt.Println("sadewm (Go) 0.1")
		os.Exit(0)
	}

	if *debugFlag {
		util.EnableDebug()
	}

	// Load TOML config
	if *configPath != "" {
		config.LoadTOML(*configPath)
	} else {
		home := util.HomePath()
		if home != "" {
			defaultPath := home + "/.config/sadewm/config.toml"
			if _, err := os.Stat(defaultPath); err == nil {
				config.LoadTOML(defaultPath)
			}
		}
	}

	// Create and set up WM
	wmgr := wm.New()
	wmgr.Setup()

	// Set up IPC
	ipcServer, err := ipc.Setup()
	if err != nil {
		util.LogDebug("ipc setup failed: %v", err)
		// Continue without IPC — non-fatal
	}

	// Apply top offset if specified
	if *topBar > 0 {
		wmgr.SetTopOffset(*topBar)
	}

	// Scan existing windows
	wmgr.Scan()

	// Run startup commands
	wmgr.Startup()

	// Handle signals for clean shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP)
	go func() {
		<-sigCh
		wmgr.Running = false
	}()

	// Main event loop
	if ipcServer != nil {
		wmgr.Run(ipcServer)
		ipcServer.Teardown()
	} else {
		wmgr.Run(nil)
	}

	wmgr.Cleanup()
}
