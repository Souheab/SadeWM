package wm

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDisplayCommandRespectsDeadline(t *testing.T) {
	directory := t.TempDir()
	script := filepath.Join(directory, "xrandr")
	if err := os.WriteFile(script, []byte("#!/bin/sh\nexec sleep 60\n"), 0755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", directory+string(os.PathListSeparator)+os.Getenv("PATH"))
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	started := time.Now()
	if _, err := runDisplayCommand(ctx, "--query"); err == nil {
		t.Fatal("unresponsive display command unexpectedly succeeded")
	}
	if time.Since(started) > 2*time.Second {
		t.Fatal("display command exceeded its cancellation bound")
	}
}
