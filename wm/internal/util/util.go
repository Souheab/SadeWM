package util

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"runtime/debug"
	"sync"
	"syscall"
)

var (
	logFile  *os.File
	Logger   *slog.Logger
	Debug    bool
	fifoPath string
	fifoFile *os.File
	fifoFD   = -1
	fifoMu   sync.Mutex
)

func LogInit(path string) {
	dir := filepath.Dir(path)
	os.MkdirAll(dir, 0755)

	var err error
	logFile, err = os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0644)
	if err != nil {
		fmt.Fprintf(os.Stderr, "sadewm: cannot open log file: %v\n", err)
		Logger = slog.New(slog.NewTextHandler(os.Stderr, nil))
		return
	}

	Logger = slog.New(slog.NewTextHandler(logFile, nil))
	Logger.Info("sadewm started")
}

// StartFIFOLog creates a named pipe (FIFO) for live log streaming.
// Consumers can read from this FIFO to get real-time stdout/stderr/debug output.
// Usage: cat ~/.local/share/sadewm/sadewm.fifo
func StartFIFOLog(path string) {
	dir := filepath.Dir(path)
	os.MkdirAll(dir, 0755)

	// Remove stale FIFO
	os.Remove(path)

	if err := syscall.Mkfifo(path, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "sadewm: cannot create FIFO %s: %v\n", path, err)
		return
	}

	fifoPath = path

	// O_RDWR keeps the FIFO open even when no reader is present (preventing
	// SIGPIPE), and O_NONBLOCK makes the open itself safe to perform here while
	// keeping raw writes from ever parking the window-manager event loop.
	fd, err := syscall.Open(path, syscall.O_RDWR|syscall.O_APPEND|syscall.O_NONBLOCK, 0)
	if err != nil {
		fmt.Fprintf(os.Stderr, "sadewm: cannot open FIFO %s: %v\n", path, err)
		return
	}
	f := os.NewFile(uintptr(fd), path)
	if f == nil {
		_ = syscall.Close(fd)
		return
	}
	fifoMu.Lock()
	fifoFile = f
	fifoFD = fd
	fifoMu.Unlock()
}

// StopFIFOLog closes and removes the FIFO.
func StopFIFOLog() {
	fifoMu.Lock()
	defer fifoMu.Unlock()
	if fifoFile != nil {
		fifoFile.Close()
		fifoFile = nil
		fifoFD = -1
	}
	if fifoPath != "" {
		os.Remove(fifoPath)
		fifoPath = ""
	}
}

// fifoWrite writes a message to the FIFO if a reader is connected.
func fifoWrite(msg string) {
	fifoMu.Lock()
	defer fifoMu.Unlock()
	if fifoFD >= 0 {
		// os.File.Write waits for readiness even on a non-blocking descriptor,
		// and calling File.Fd again can return it to blocking mode when the Go
		// poller owns the file. Retain the descriptor captured at setup instead.
		// Use the raw syscall so EAGAIN really means "drop this live-log
		// message" instead of parking the window-manager event loop.
		_, _ = syscall.Write(fifoFD, []byte(msg))
	}
}

func Die(format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	fmt.Fprintln(os.Stderr, msg)
	fifoWrite("FATAL: " + msg + "\n")
	if Logger != nil {
		Logger.Error("fatal", "msg", msg)
	}
	os.Exit(1)
}

func LogDebug(format string, args ...any) {
	if !Debug {
		return
	}
	msg := fmt.Sprintf(format, args...)
	if Logger != nil {
		Logger.Debug(msg)
	} else {
		fmt.Fprintln(os.Stderr, "DEBUG: "+msg)
	}
	fifoWrite("DEBUG: " + msg + "\n")
}

func LogDebugf(format string, args ...any) {
	LogDebug(format, args...)
}

// LogInfo logs an informational message to both the log file and the FIFO.
func LogInfo(format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	if Logger != nil {
		Logger.Info(msg)
	}
	fifoWrite("INFO: " + msg + "\n")
}

func CrashHandler() {
	if r := recover(); r != nil {
		msg := fmt.Sprintf("sadewm: crash: %v\nStack trace:\n%s\n", r, debug.Stack())
		if logFile != nil {
			fmt.Fprint(logFile, msg)
		}
		fifoWrite(msg)
		fmt.Fprintf(os.Stderr, "sadewm: crash: %v\n", r)
	}
}

func EnableDebug() {
	Debug = true
}

func HomePath() string {
	return os.Getenv("HOME")
}
