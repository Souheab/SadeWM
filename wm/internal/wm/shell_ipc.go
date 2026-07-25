package wm

import (
	"bufio"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

const shellIPCDeadline = 250 * time.Millisecond

func normalizedShellDisplay(display string) string {
	if display == "" {
		display = ":0"
	}
	if dot := strings.LastIndex(display, "."); dot >= 0 {
		suffix := display[dot+1:]
		if suffix != "" && strings.IndexFunc(suffix, func(r rune) bool {
			return r < '0' || r > '9'
		}) == -1 {
			display = display[:dot]
		}
	}
	display = strings.TrimLeft(display, ":")
	display = strings.ReplaceAll(display, "/", "_")
	if display == "" {
		return "0"
	}
	return display
}

func shellSocketCandidates(display, runtimeDir string) []string {
	filename := fmt.Sprintf(
		"sadeshell-%s.sock", normalizedShellDisplay(display),
	)
	directories := []string{}
	if runtimeDir != "" {
		directories = append(directories, runtimeDir)
	}
	directories = append(directories, "/tmp")

	seen := map[string]bool{}
	paths := make([]string, 0, len(directories))
	for _, directory := range directories {
		path := filepath.Join(directory, filename)
		if !seen[path] {
			seen[path] = true
			paths = append(paths, path)
		}
	}
	return paths
}

func sendShellCommand(command string) error {
	var failures []string
	for _, path := range shellSocketCandidates(
		os.Getenv("DISPLAY"), os.Getenv("XDG_RUNTIME_DIR"),
	) {
		conn, err := net.DialTimeout("unix", path, shellIPCDeadline)
		if err != nil {
			failures = append(failures, fmt.Sprintf("%s: %v", path, err))
			continue
		}
		_ = conn.SetDeadline(time.Now().Add(shellIPCDeadline))
		_, writeErr := fmt.Fprintf(conn, "%s\n", command)
		if writeErr != nil {
			_ = conn.Close()
			failures = append(failures, fmt.Sprintf("%s: %v", path, writeErr))
			continue
		}
		response, readErr := bufio.NewReader(conn).ReadString('\n')
		_ = conn.Close()
		if readErr == nil && strings.TrimSpace(response) == "ok" {
			return nil
		}
		if readErr != nil {
			failures = append(failures, fmt.Sprintf("%s: %v", path, readErr))
		} else {
			failures = append(
				failures,
				fmt.Sprintf("%s: unexpected response %q", path, response),
			)
		}
	}
	return errors.New(strings.Join(failures, "; "))
}

func shellCommandFlag(command string) string {
	switch command {
	case "open-window-picker":
		return "--open-window-picker"
	case "open-minimized-picker":
		return "--open-minimized-picker"
	default:
		return ""
	}
}

func shellCommandFromArgv(argv []string) string {
	if len(argv) != 2 || argv[0] != "sadeshell" {
		return ""
	}
	switch argv[1] {
	case "--open-window-picker":
		return "open-window-picker"
	case "--open-minimized-picker":
		return "open-minimized-picker"
	default:
		return ""
	}
}

// ShellCommand sends a picker command directly to the resident shell. The
// legacy command-line client remains a fallback for unusual socket setups.
func (wm *WM) ShellCommand(arg *config.Arg) {
	if arg == nil {
		return
	}
	command, ok := arg.V.(string)
	if !ok || command == "" {
		return
	}
	wm.sendShellCommandAsync(command)
}

func (wm *WM) sendShellCommandAsync(command string) {
	go func() {
		if err := sendShellCommand(command); err == nil {
			return
		} else {
			util.LogDebugf("sadeshell IPC %q failed: %v", command, err)
		}
		if flag := shellCommandFlag(command); flag != "" {
			wm.spawnCmd([]string{"sadeshell", flag})
		}
	}()
}
