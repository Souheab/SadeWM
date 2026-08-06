package util

import (
	"os"
	"syscall"
	"testing"
	"time"
)

func TestFIFOWriteDoesNotBlockWhenPipeIsFull(t *testing.T) {
	var fds [2]int
	if err := syscall.Pipe(fds[:]); err != nil {
		t.Fatal(err)
	}
	reader := os.NewFile(uintptr(fds[0]), "fifo-test-reader")
	writer := os.NewFile(uintptr(fds[1]), "fifo-test-writer")
	defer reader.Close()
	defer writer.Close()
	if err := syscall.SetNonblock(fds[1], true); err != nil {
		t.Fatal(err)
	}

	chunk := make([]byte, 4096)
	for {
		if _, err := syscall.Write(fds[1], chunk); err != nil {
			if err == syscall.EAGAIN || err == syscall.EWOULDBLOCK {
				break
			}
			t.Fatal(err)
		}
	}

	fifoMu.Lock()
	previous := fifoFile
	previousFD := fifoFD
	fifoFile = writer
	fifoFD = fds[1]
	fifoMu.Unlock()
	defer func() {
		fifoMu.Lock()
		fifoFile = previous
		fifoFD = previousFD
		fifoMu.Unlock()
	}()

	done := make(chan struct{})
	go func() {
		fifoWrite("message that may be dropped")
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("fifoWrite blocked on a full pipe")
	}
}
