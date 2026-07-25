package wm

import (
	"bufio"
	"fmt"
	"net"
	"path/filepath"
	"testing"
)

func TestShellSocketCandidatesMatchShellNaming(t *testing.T) {
	got := shellSocketCandidates(":7.0", "/run/user/1000")
	want := []string{
		"/run/user/1000/sadeshell-7.sock",
		"/tmp/sadeshell-7.sock",
	}
	if len(got) != len(want) {
		t.Fatalf("got %v, want %v", got, want)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("got %v, want %v", got, want)
		}
	}
}

func TestShellCommandFromLegacyPickerArgv(t *testing.T) {
	if got := shellCommandFromArgv([]string{
		"sadeshell", "--open-window-picker",
	}); got != "open-window-picker" {
		t.Fatalf("got command %q", got)
	}
	if got := shellCommandFromArgv([]string{
		"sadeshell", "--open-launcher",
	}); got != "" {
		t.Fatalf("unexpected command %q", got)
	}
}

func TestSendShellCommandUsesResidentSocket(t *testing.T) {
	runtimeDir := t.TempDir()
	t.Setenv("DISPLAY", ":42.0")
	t.Setenv("XDG_RUNTIME_DIR", runtimeDir)
	socketPath := filepath.Join(runtimeDir, "sadeshell-42.sock")
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()

	received := make(chan string, 1)
	go func() {
		conn, acceptErr := listener.Accept()
		if acceptErr != nil {
			received <- fmt.Sprintf("accept error: %v", acceptErr)
			return
		}
		defer conn.Close()
		command, readErr := bufio.NewReader(conn).ReadString('\n')
		if readErr != nil {
			received <- fmt.Sprintf("read error: %v", readErr)
			return
		}
		received <- command
		_, _ = conn.Write([]byte("ok\n"))
	}()

	if err := sendShellCommand("open-window-picker"); err != nil {
		t.Fatal(err)
	}
	if command := <-received; command != "open-window-picker\n" {
		t.Fatalf("got command %q", command)
	}
}
