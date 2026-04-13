package wm

import (
	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/xproto"
	"github.com/BurntSushi/xgbutil"

	"github.com/sadewm/sadewm/wm/internal/config"
)

// Client represents a managed window.
type Client struct {
	Name string
	// Aspect ratio hints
	MinA, MaxA float32
	// Current geometry
	X, Y, W, H int
	// Saved geometry (for fullscreen/maximize restore)
	OldX, OldY, OldW, OldH int
	// Size hints
	BaseW, BaseH, IncW, IncH, MaxW, MaxH, MinW, MinH int
	HintsValid                                       bool
	// Border width
	BW, OldBW int
	// Tags bitmask
	Tags uint32
	// State flags
	IsFixed, IsFloating, IsUrgent, NeverFocus bool
	OldState                                  bool // was floating before fullscreen
	IsFullscreen                              bool
	Maximized                                 bool
	Minimized                                 bool
	IsAbove                                   bool
	IsDock                                    bool

	// Linked list pointers
	Next  *Client
	SNext *Client // stack order
	Mon   *Monitor
	Win   xproto.Window
}

// Tag stores per-tag state.
type Tag struct {
	TagNum       int
	Lt           *config.Layout
	MFact        float32
	NMaster      int
	IsRightTiled bool
}

// Monitor represents a physical screen.
type Monitor struct {
	LtSymbol string
	MFact    float32
	NMaster  int
	Num      int
	// Screen geometry
	MX, MY, MW, MH int
	// Working area (excluding offsets)
	WX, WY, WW, WH int
	GapPx          int

	SelTags uint32
	TagSet  [2]uint32

	Clients *Client
	Sel     *Client
	Stack   *Client
	Next    *Monitor

	Lt           *config.Layout
	Tags         []Tag
	IsRightTiled bool
}

// WM holds the entire window manager state.
type WM struct {
	X    *xgbutil.XUtil
	Conn *xgb.Conn // raw connection
	Root xproto.Window

	Screen     *xproto.ScreenInfo
	SW, SH     int // screen width, height
	ScreenNum  int
	WMCheckWin xproto.Window

	// Monitors
	Mons   *Monitor
	SelMon *Monitor

	// Atoms
	WMAtom  [WMLast]xproto.Atom
	NetAtom [NetLast]xproto.Atom
	UTF8    xproto.Atom

	// Cursors
	Cursors [CurLast]xproto.Cursor

	// Border colors
	BorderNorm uint32
	BorderSel  uint32

	// Numlock
	NumlockMask uint16

	// Running state
	Running bool
	Debug   bool

	// Config
	ActiveRules []config.Rule
	ActiveKeys  []config.Key
	Layouts     []config.Layout
	CfgPath     string

	// Minimize stack
	MinimizeStack []*Client

	// Event delivery: all X events are fed through this channel by a
	// background goroutine so the main loop can select between X events
	// and IPC requests without blocking indefinitely.
	XEvCh chan xgbEvent

	// Events buffered during a drag that should be re-processed after.
	pendingEvts []xgb.Event

	// Action dispatch table
	Actions map[string]config.ActionFunc
}

// Atom enums
const (
	NetSupported = iota
	NetWMName
	NetWMState
	NetWMCheck
	NetWMFullscreen
	NetActiveWindow
	NetWMWindowType
	NetWMStateAbove
	NetWMStateStaysOnTop
	NetWMWindowTypeDialog
	NetWMWindowTypeDock
	NetClientList
	NetWMWindowTypeUtility
	NetWMWindowTypeSplash
	NetWMWindowTypeToolbar
	NetWMWindowTypePopupMenu
	NetWMWindowTypeDropdownMenu
	NetWMWindowTypeTooltip
	NetWMWindowTypeNotification
	NetLast
)

const (
	WMProtocols = iota
	WMDelete
	WMState
	WMTakeFocus
	WMLast
)

// Cursor types
const (
	CurNormal = iota
	CurResize
	CurMove
	CurLast
)

// TagMask returns the bitmask for all valid tags.
func TagMask() uint32 {
	return (1 << uint(len(config.Tags))) - 1
}

// IsVisible returns whether a client is visible on its monitor's current tagset.
func (c *Client) IsVisible() bool {
	return (c.Tags&c.Mon.TagSet[c.Mon.SelTags]) != 0 && !c.Minimized
}

// Width returns the total width including borders.
func (c *Client) Width() int {
	return c.W + 2*c.BW
}

// Height returns the total height including borders.
func (c *Client) Height() int {
	return c.H + 2*c.BW
}

// Intersect calculates the intersection area between a rect and a monitor's working area.
func Intersect(x, y, w, h int, m *Monitor) int {
	overlapX := max(0, min(x+w, m.WX+m.WW)-max(x, m.WX))
	overlapY := max(0, min(y+h, m.WY+m.WH)-max(y, m.WY))
	return overlapX * overlapY
}

// CreateMon creates a new Monitor with default values.
func CreateMon(layouts []config.Layout) *Monitor {
	m := &Monitor{
		MFact:   float32(config.MFact),
		NMaster: config.NMaster,
		GapPx:   int(config.GapPx),
	}
	m.TagSet[0] = 1
	m.TagSet[1] = 1

	if len(layouts) > 0 {
		m.Lt = &layouts[0]
		m.LtSymbol = layouts[0].Symbol
	}

	m.Tags = make([]Tag, len(config.Tags))
	for i := range config.Tags {
		m.Tags[i] = Tag{
			TagNum:       i,
			Lt:           m.Lt,
			MFact:        m.MFact,
			NMaster:      m.NMaster,
			IsRightTiled: false,
		}
	}
	m.IsRightTiled = false
	return m
}
