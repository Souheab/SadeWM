package util

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"runtime/debug"
)

var (
	logFile *os.File
	Logger  *slog.Logger
	Debug   bool
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

func Die(format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	fmt.Fprintln(os.Stderr, msg)
	if Logger != nil {
		Logger.Error("fatal", "msg", msg)
	}
	os.Exit(1)
}

func LogDebug(format string, args ...any) {
	if Debug {
		fmt.Printf("DEBUG LOG: "+format+"\n", args...)
	}
}

func LogDebugf(format string, args ...any) {
	if Debug {
		fmt.Printf("DEBUG LOG: "+format+"\n", args...)
	}
}

func CrashHandler() {
	if r := recover(); r != nil {
		if logFile != nil {
			fmt.Fprintf(logFile, "sadewm: crash: %v\nStack trace:\n%s\n", r, debug.Stack())
		}
		fmt.Fprintf(os.Stderr, "sadewm: crash: %v\n", r)
	}
}

func EnableDebug() {
	Debug = true
}

func HomePath() string {
	return os.Getenv("HOME")
}
