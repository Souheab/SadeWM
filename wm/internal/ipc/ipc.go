package ipc

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/sadewm/sadewm/wm/internal/util"
)

const maxRequestBytes = 64 * 1024

var ioTimeout = 2 * time.Second

// GetSocketPath returns the Unix socket path for the current DISPLAY.
// If SADEWM_SOCKET is set it is used as-is.
// Otherwise the path is derived from the DISPLAY env var so that nested
// (test) instances on different displays each get their own socket and
// don't clobber each other.
// Examples: DISPLAY=:0  → /tmp/sadewm-0.sock
//
//	DISPLAY=:1  → /tmp/sadewm-1.sock
//	unset       → /tmp/sadewm.sock
func GetSocketPath() string {
	if p := os.Getenv("SADEWM_SOCKET"); p != "" {
		return p
	}
	display := os.Getenv("DISPLAY")
	if display == "" {
		return "/tmp/sadewm.sock"
	}
	// Strip leading ':' and replace any '.' with '-' to build a safe filename.
	safe := strings.TrimPrefix(display, ":")
	safe = strings.ReplaceAll(safe, ".", "-")
	return fmt.Sprintf("/tmp/sadewm-%s.sock", safe)
}

// IPCRequest is a single IPC request parsed from JSON, bundled with
// a response channel so the main event loop can reply.
type IPCRequest struct {
	Cmd        string `json:"cmd"`
	Mask       uint32 `json:"mask,omitempty"`
	WinID      uint32 `json:"win_id,omitempty"`
	ResponseCh chan *Response
}

// TagEvent is a streamed tag-state update for subscription clients.
type TagEvent struct {
	Event     string   `json:"event"`
	TagMask   uint32   `json:"tag_mask"`
	TagsState []string `json:"tags_state"`
}

// Response is the JSON reply written back to the client.
type Response struct {
	OK        bool         `json:"ok"`
	Error     string       `json:"error,omitempty"`
	TagMask   uint32       `json:"tag_mask,omitempty"`
	Layout    string       `json:"layout,omitempty"`
	MFact     float64      `json:"mfact,omitempty"`
	NMaster   int          `json:"nmaster,omitempty"`
	Gaps      int          `json:"gaps,omitempty"`
	RightTile bool         `json:"isrighttiled,omitempty"`
	Clients   []ClientDTO  `json:"clients,omitempty"`
	TagsState []string     `json:"tags_state,omitempty"`
	Keybinds  []KeybindDTO `json:"keybinds,omitempty"`
}

// ClientDTO is the per-client info returned in get_state.
type ClientDTO struct {
	Name      string `json:"name"`
	WinID     uint32 `json:"win_id"`
	Class     string `json:"class"`
	Tags      uint32 `json:"tags"`
	Floating  bool   `json:"floating"`
	Maximized bool   `json:"maximized"`
	Focused   bool   `json:"focused"`
	Minimized bool   `json:"minimized"`
}

// KeybindDTO is the per-keybinding info returned in keybinds.
type KeybindDTO struct {
	Mod         []string `json:"mod"`
	Key         string   `json:"key"`
	Action      string   `json:"action"`
	Description string   `json:"description"`
}

// Server is the Unix-socket IPC listener.
type Server struct {
	listener       net.Listener
	socketPath     string
	reqCh          chan *IPCRequest
	mu             sync.Mutex
	closed         bool
	tagSubMu       sync.Mutex
	tagSubscribers map[*tagSubscriber]struct{}
}

type tagSubscriber struct {
	ch chan TagEvent
}

// Setup creates the Unix socket and starts listening.
func Setup() (*Server, error) {
	sockPath := GetSocketPath()

	// Remove stale socket from a previous run
	os.Remove(sockPath)

	ln, err := net.Listen("unix", sockPath)
	if err != nil {
		return nil, fmt.Errorf("ipc: listen: %w", err)
	}

	return &Server{
		listener:       ln,
		socketPath:     sockPath,
		reqCh:          make(chan *IPCRequest, 8),
		tagSubscribers: make(map[*tagSubscriber]struct{}),
	}, nil
}

// RequestChan returns the channel that delivers parsed IPC requests
// to the main event loop.
func (s *Server) RequestChan() <-chan *IPCRequest {
	return s.reqCh
}

// Run accepts connections in a loop. Call in a goroutine.
// Each connection is handled synchronously (one message per connection).
func (s *Server) Run() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			s.mu.Lock()
			closed := s.closed
			s.mu.Unlock()
			if closed {
				return
			}
			util.LogDebug("ipc: accept error: %v", err)
			continue
		}
		go s.handleConn(conn)
	}
}

func (s *Server) handleConn(conn net.Conn) {
	defer conn.Close()

	_ = conn.SetReadDeadline(time.Now().Add(ioTimeout))
	data, err := io.ReadAll(io.LimitReader(conn, maxRequestBytes+1))
	if err != nil || len(data) == 0 {
		return
	}
	if len(data) > maxRequestBytes {
		s.writeResponse(conn, &Response{OK: false, Error: "request too large"})
		return
	}

	var req IPCRequest
	if err := json.Unmarshal(data, &req); err != nil {
		s.writeResponse(conn, &Response{OK: false, Error: "invalid JSON"})
		return
	}
	if req.Cmd == "subscribe_tags" {
		s.handleTagSubscription(conn, &req)
		return
	}

	// Send request to the main event loop and wait for the response
	req.ResponseCh = make(chan *Response, 1)
	select {
	case s.reqCh <- &req:
	case <-time.After(ioTimeout):
		s.writeResponse(conn, &Response{OK: false, Error: "window manager busy"})
		return
	}

	var resp *Response
	select {
	case resp = <-req.ResponseCh:
	case <-time.After(ioTimeout):
		s.writeResponse(conn, &Response{OK: false, Error: "window manager response timed out"})
		return
	}
	if resp == nil {
		resp = &Response{OK: false, Error: "unknown command"}
	}

	s.writeResponse(conn, resp)
}

func (s *Server) handleTagSubscription(conn net.Conn, req *IPCRequest) {
	sub := s.addTagSubscriber()
	defer s.removeTagSubscriber(sub)

	req.ResponseCh = make(chan *Response, 1)
	select {
	case s.reqCh <- req:
	case <-time.After(ioTimeout):
		s.writeResponse(conn, &Response{OK: false, Error: "window manager busy"})
		return
	}

	var resp *Response
	select {
	case resp = <-req.ResponseCh:
	case <-time.After(ioTimeout):
		s.writeResponse(conn, &Response{OK: false, Error: "window manager response timed out"})
		return
	}
	if resp == nil || !resp.OK {
		if resp == nil {
			resp = &Response{OK: false, Error: "unknown command"}
		}
		s.writeResponse(conn, resp)
		return
	}

	initial := TagEvent{
		Event:     "tags_state",
		TagMask:   resp.TagMask,
		TagsState: append([]string(nil), resp.TagsState...),
	}
	if err := s.writeTagEvent(conn, initial); err != nil {
		return
	}

	for ev := range sub.ch {
		if err := s.writeTagEvent(conn, ev); err != nil {
			return
		}
	}
}

func (s *Server) writeResponse(conn net.Conn, resp *Response) {
	data, _ := json.Marshal(resp)
	data = append(data, '\n')
	_ = conn.SetWriteDeadline(time.Now().Add(ioTimeout))
	_, _ = conn.Write(data)
}

func (s *Server) writeTagEvent(conn net.Conn, ev TagEvent) error {
	ev.TagsState = append([]string(nil), ev.TagsState...)
	data, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	_ = conn.SetWriteDeadline(time.Now().Add(ioTimeout))
	_, err = conn.Write(data)
	return err
}

func (s *Server) ensureTagSubscribers() {
	if s.tagSubscribers == nil {
		s.tagSubscribers = make(map[*tagSubscriber]struct{})
	}
}

func (s *Server) addTagSubscriber() *tagSubscriber {
	sub := &tagSubscriber{ch: make(chan TagEvent, 1)}
	s.tagSubMu.Lock()
	s.ensureTagSubscribers()
	s.tagSubscribers[sub] = struct{}{}
	s.tagSubMu.Unlock()
	return sub
}

func (s *Server) removeTagSubscriber(sub *tagSubscriber) {
	s.tagSubMu.Lock()
	delete(s.tagSubscribers, sub)
	s.tagSubMu.Unlock()
}

// BroadcastTags queues the newest tag event for every active subscriber.
// Slow subscribers never block the WM; their stale queued event is replaced.
func (s *Server) BroadcastTags(ev TagEvent) int {
	ev.TagsState = append([]string(nil), ev.TagsState...)

	s.tagSubMu.Lock()
	defer s.tagSubMu.Unlock()
	s.ensureTagSubscribers()

	for sub := range s.tagSubscribers {
		select {
		case sub.ch <- ev:
		default:
			select {
			case <-sub.ch:
			default:
			}
			select {
			case sub.ch <- ev:
			default:
			}
		}
	}
	return len(s.tagSubscribers)
}

// TagSubscriberCount returns the number of active tag stream subscribers.
func (s *Server) TagSubscriberCount() int {
	s.tagSubMu.Lock()
	defer s.tagSubMu.Unlock()
	return len(s.tagSubscribers)
}

// Teardown closes the listener and removes the socket file.
func (s *Server) Teardown() {
	s.mu.Lock()
	s.closed = true
	s.mu.Unlock()

	s.listener.Close()
	os.Remove(s.socketPath)
}
