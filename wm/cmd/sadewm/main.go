package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/ipc"
	"github.com/sadewm/sadewm/wm/internal/util"
	"github.com/sadewm/sadewm/wm/internal/wm"
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

	// Initialize logging (file + FIFO for live log access)
	if home := util.HomePath(); home != "" {
		util.LogInit(home + "/.local/share/sadewm/sadewm.log")
		util.StartFIFOLog(home + "/.local/share/sadewm/sadewm.fifo")
	} else {
		util.LogInit("")
	}

	// Load and apply TOML config
	var tc *config.TOMLConfig
	var cfgPath string
	if *configPath != "" {
		cfgPath = *configPath
		tc = config.LoadTOML(cfgPath)
	} else {
		home := util.HomePath()
		if home != "" {
			defaultPath := home + "/.config/sadewm/config.toml"
			if _, err := os.Stat(defaultPath); err == nil {
				cfgPath = defaultPath
				tc = config.LoadTOML(cfgPath)
			}
		}
	}
	config.ApplyTOML(tc)

	// Create and set up WM
	wmgr := wm.New()
	wmgr.CfgPath = cfgPath
	wmgr.Setup()

	// Set up IPC
	ipcServer, err := ipc.Setup()
	if err != nil {
		util.LogDebug("ipc setup failed: %v", err)
		// Continue without IPC — non-fatal
	}

	// Apply top/bottom offsets from config (CLI flag overrides config)
	if *topBar > 0 {
		wmgr.SetTopOffset(*topBar)
	} else if config.TopOffset > 0 {
		wmgr.SetTopOffset(config.TopOffset)
	}
	if config.BottomOffset > 0 {
		wmgr.SetBottomOffset(config.BottomOffset)
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

	// SIGUSR1: dump goroutine stacks + WM state to log and FIFO.
	// Usage: kill -USR1 $(pidof sadewm)
	usr1Ch := make(chan os.Signal, 1)
	signal.Notify(usr1Ch, syscall.SIGUSR1)
	go func() {
		for range usr1Ch {
			buf := make([]byte, 1<<20) // 1 MiB — enough for all goroutines
			n := runtime.Stack(buf, true)
			report := wmgr.DebugInfo() + "\n=== goroutine dump ===\n" + string(buf[:n]) + "\n"
			util.LogInfo("SIGUSR1 debug report:\n%s", report)
		}
	}()

	// Main event loop
	if ipcServer != nil {
		wmgr.Run(ipcServer)
		ipcServer.Teardown()
	} else {
		wmgr.Run(nil)
	}

	wmgr.Cleanup()
	util.StopFIFOLog()
}
