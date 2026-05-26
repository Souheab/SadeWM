package ipc

import (
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
	"time"
)

func roundTrip(t *testing.T, s *Server, payload []byte) *Response {
	t.Helper()

	path := filepath.Join(t.TempDir(), "sadewm.sock")
	ln, err := net.Listen("unix", path)
	if err != nil {
		t.Fatalf("listen unix: %v", err)
	}
	defer ln.Close()

	errCh := make(chan error, 1)
	go func() {
		conn, err := ln.Accept()
		if err != nil {
			errCh <- err
			return
		}
		s.handleConn(conn)
		errCh <- nil
	}()

	conn, err := net.Dial("unix", path)
	if err != nil {
		t.Fatalf("dial unix: %v", err)
	}
	defer conn.Close()

	if _, err := conn.Write(payload); err != nil {
		t.Fatalf("write request: %v", err)
	}
	if unixConn, ok := conn.(*net.UnixConn); ok {
		if err := unixConn.CloseWrite(); err != nil {
			t.Fatalf("close write: %v", err)
		}
	}

	var resp Response
	if err := json.NewDecoder(conn).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if err := <-errCh; err != nil {
		t.Fatalf("server error: %v", err)
	}
	return &resp
}

func withShortTimeout(t *testing.T) {
	t.Helper()
	old := ioTimeout
	ioTimeout = 20 * time.Millisecond
	t.Cleanup(func() { ioTimeout = old })
}

func TestHandleConnInvalidJSON(t *testing.T) {
	resp := roundTrip(t, &Server{reqCh: make(chan *IPCRequest, 1)}, []byte("{"))
	if resp.OK || resp.Error != "invalid JSON" {
		t.Fatalf("unexpected response: %+v", resp)
	}
}

func TestHandleConnOversizedRequest(t *testing.T) {
	payload := make([]byte, maxRequestBytes+1)
	for i := range payload {
		payload[i] = 'x'
	}
	resp := roundTrip(t, &Server{reqCh: make(chan *IPCRequest, 1)}, payload)
	if resp.OK || resp.Error != "request too large" {
		t.Fatalf("unexpected response: %+v", resp)
	}
}

func TestHandleConnBusyTimeout(t *testing.T) {
	withShortTimeout(t)
	resp := roundTrip(t, &Server{reqCh: make(chan *IPCRequest)}, []byte(`{"cmd":"get_state"}`))
	if resp.OK || resp.Error != "window manager busy" {
		t.Fatalf("unexpected response: %+v", resp)
	}
}

func TestHandleConnResponseTimeout(t *testing.T) {
	withShortTimeout(t)
	resp := roundTrip(t, &Server{reqCh: make(chan *IPCRequest, 1)}, []byte(`{"cmd":"get_state"}`))
	if resp.OK || resp.Error != "window manager response timed out" {
		t.Fatalf("unexpected response: %+v", resp)
	}
}
