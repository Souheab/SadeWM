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

func TestSubscribeTagsSendsInitialEvent(t *testing.T) {
	s := &Server{reqCh: make(chan *IPCRequest, 1)}
	client, errCh := dialHandledConn(t, s)
	defer client.Close()

	if _, err := client.Write([]byte(`{"cmd":"subscribe_tags"}`)); err != nil {
		t.Fatalf("write request: %v", err)
	}
	if err := client.(*net.UnixConn).CloseWrite(); err != nil {
		t.Fatalf("close write: %v", err)
	}

	req := <-s.reqCh
	if req.Cmd != "subscribe_tags" {
		t.Fatalf("unexpected request: %+v", req)
	}
	req.ResponseCh <- &Response{
		OK:        true,
		TagMask:   1,
		TagsState: []string{"A", "I"},
	}

	var ev TagEvent
	if err := json.NewDecoder(client).Decode(&ev); err != nil {
		t.Fatalf("decode event: %v", err)
	}
	if ev.Event != "tags_state" || ev.TagMask != 1 || len(ev.TagsState) != 2 || ev.TagsState[0] != "A" {
		t.Fatalf("unexpected event: %+v", ev)
	}

	client.Close()
	s.BroadcastTags(TagEvent{Event: "tags_state", TagMask: 2, TagsState: []string{"I", "A"}})
	select {
	case <-errCh:
	case <-time.After(time.Second):
		t.Fatal("subscription handler did not exit after client close and broadcast")
	}
}

func TestBroadcastTagsReplacesStaleQueuedEvent(t *testing.T) {
	s := &Server{}
	sub := s.addTagSubscriber()
	defer s.removeTagSubscriber(sub)

	s.BroadcastTags(TagEvent{Event: "tags_state", TagMask: 1, TagsState: []string{"A"}})
	s.BroadcastTags(TagEvent{Event: "tags_state", TagMask: 2, TagsState: []string{"I", "A"}})
	s.BroadcastTags(TagEvent{Event: "tags_state", TagMask: 4, TagsState: []string{"I", "I", "A"}})

	var last TagEvent
	for {
		select {
		case last = <-sub.ch:
		default:
			if last.TagMask != 4 {
				t.Fatalf("expected newest event to survive, got %+v", last)
			}
			return
		}
	}
}

func TestSubscribeTagsRemovesSubscriberOnWriteFailure(t *testing.T) {
	s := &Server{reqCh: make(chan *IPCRequest, 1)}
	client, errCh := dialHandledConn(t, s)

	if _, err := client.Write([]byte(`{"cmd":"subscribe_tags"}`)); err != nil {
		t.Fatalf("write request: %v", err)
	}
	if err := client.(*net.UnixConn).CloseWrite(); err != nil {
		t.Fatalf("close write: %v", err)
	}

	req := <-s.reqCh
	req.ResponseCh <- &Response{OK: true, TagMask: 1, TagsState: []string{"A"}}

	var ev TagEvent
	if err := json.NewDecoder(client).Decode(&ev); err != nil {
		t.Fatalf("decode initial event: %v", err)
	}
	if count := s.TagSubscriberCount(); count != 1 {
		t.Fatalf("expected 1 subscriber, got %d", count)
	}

	client.Close()
	s.BroadcastTags(TagEvent{Event: "tags_state", TagMask: 2, TagsState: []string{"I", "A"}})

	select {
	case <-errCh:
	case <-time.After(time.Second):
		t.Fatal("subscription handler did not exit")
	}
	if count := s.TagSubscriberCount(); count != 0 {
		t.Fatalf("expected subscriber cleanup, got %d", count)
	}
}

func dialHandledConn(t *testing.T, s *Server) (net.Conn, <-chan error) {
	t.Helper()

	path := filepath.Join(t.TempDir(), "sadewm.sock")
	ln, err := net.Listen("unix", path)
	if err != nil {
		t.Fatalf("listen unix: %v", err)
	}
	t.Cleanup(func() { ln.Close() })

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

	client, err := net.Dial("unix", path)
	if err != nil {
		t.Fatalf("dial unix: %v", err)
	}
	return client, errCh
}
