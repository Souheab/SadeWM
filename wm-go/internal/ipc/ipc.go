package ipc

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"

	"github.com/sadewm/sadewm/wm-go/internal/util"
)

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
	ResponseCh chan *Response
}

// Response is the JSON reply written back to the client.
type Response struct {
	OK        bool        `json:"ok"`
	Error     string      `json:"error,omitempty"`
	TagMask   uint32      `json:"tag_mask,omitempty"`
	Layout    string      `json:"layout,omitempty"`
	MFact     float64     `json:"mfact,omitempty"`
	NMaster   int         `json:"nmaster,omitempty"`
	Gaps      int         `json:"gaps,omitempty"`
	RightTile bool        `json:"isrighttiled,omitempty"`
	Clients   []ClientDTO `json:"clients,omitempty"`
	TagsState []string    `json:"tags_state,omitempty"`
}

// ClientDTO is the per-client info returned in get_state.
type ClientDTO struct {
	Name      string `json:"name"`
	Tags      uint32 `json:"tags"`
	Floating  bool   `json:"floating"`
	Maximized bool   `json:"maximized"`
	Focused   bool   `json:"focused"`
}

// Server is the Unix-socket IPC listener.
type Server struct {
	listener   net.Listener
	socketPath string
	reqCh      chan *IPCRequest
	mu         sync.Mutex
	closed     bool
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
		listener:   ln,
		socketPath: sockPath,
		reqCh:      make(chan *IPCRequest, 8),
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

	buf := make([]byte, 4096)
	n, err := conn.Read(buf)
	if err != nil || n == 0 {
		return
	}

	var req IPCRequest
	if err := json.Unmarshal(buf[:n], &req); err != nil {
		resp := &Response{OK: false, Error: "invalid JSON"}
		data, _ := json.Marshal(resp)
		data = append(data, '\n')
		conn.Write(data)
		return
	}

	// Send request to the main event loop and wait for the response
	req.ResponseCh = make(chan *Response, 1)
	s.reqCh <- &req

	resp := <-req.ResponseCh
	if resp == nil {
		resp = &Response{OK: false, Error: "unknown command"}
	}

	data, _ := json.Marshal(resp)
	data = append(data, '\n')
	conn.Write(data)
}

// Teardown closes the listener and removes the socket file.
func (s *Server) Teardown() {
	s.mu.Lock()
	s.closed = true
	s.mu.Unlock()

	s.listener.Close()
	os.Remove(s.socketPath)
}
