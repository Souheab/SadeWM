package wm

import (
	"sync"
	"sync/atomic"
	"unsafe"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
	"github.com/jezek/xgbutil"

	"github.com/sadewm/sadewm/wm/internal/config"
)

// Suppress "unsafe imported and not used" when CGo is the sole consumer.
var _ = unsafe.Pointer(nil)

// Client represents a managed window.
type Client struct {
	Name string
	// Aspect ratio hints
	MinA, MaxA float32
	// Current geometry
	X, Y, W, H int
	// Saved geometry (for fullscreen/maximize restore)
	OldX, OldY, OldW, OldH int
	// Dedicated pre-fullscreen geometry. Old* is updated by every resize, so it
	// cannot safely survive a root/display resize while the client is fullscreen.
	FullscreenX, FullscreenY, FullscreenW, FullscreenH int
	FullscreenRestoreValid                             bool
	// Size hints
	BaseW, BaseH, IncW, IncH, MaxW, MaxH, MinW, MinH int
	HintsValid                                       bool
	// Border width
	BW, OldBW int
	// Tags bitmask
	Tags uint32
	// State flags
	IsFixed, IsFloating, IsUrgent, NeverFocus bool
	HasPositionHint                           bool
	OldState                                  bool // was floating before fullscreen
	IsFullscreen                              bool
	Maximized                                 bool
	Minimized                                 bool
	IsAbove                                   bool
	IsDock                                    bool
	HasMapped                                 bool

	// Linked list pointers
	Next  *Client
	SNext *Client // stack order
	Mon   *Monitor
	Win   xproto.Window

	// Titlebar (non-zero only for floating windows)
	BorderWin   xproto.Window
	FrameWin    xproto.Window
	TitleWin    xproto.Window
	TitleHover  titleButton // button currently hovered (tbNone when none)
	IgnoreUnmap int         // WM-initiated reparent notifications to discard
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

	// Root wallpaper pixmap advertised through _XROOTPMAP_ID/ESETROOT_PMAP_ID
	// for compositors such as picom. Keep this pixmap alive while it is
	// referenced by the root window and root pixmap properties.
	WallpaperPixmap xproto.Pixmap

	// Numlock
	NumlockMask uint16

	// Running state
	Running  atomic.Bool
	Debug    bool
	QuitCh   chan struct{}
	quitOnce sync.Once

	// Work-area offsets
	TopOffset    uint
	BottomOffset uint

	// Config
	ActiveRules  []config.Rule
	ActiveKeys   []config.Key
	Layouts      []config.Layout
	CfgPath      string
	SettingsPath string
	StartupPath  string
	NoConfig     bool

	// X11 session power settings
	sleepTimeoutMinutes int
	sleepTriggered      bool

	// Minimize stack
	MinimizeStack []*Client

	// Event delivery: all X events are fed through this channel by a
	// background goroutine so the main loop can select between X events
	// and IPC requests without blocking indefinitely.
	XEvCh chan xgbEvent

	// Events buffered during a drag that should be re-processed after.
	pendingEvts []xgb.Event

	lastTagMask           uint32
	lastTagsState         []string
	lastTagsSnapshotValid bool

	// dragging is true while MoveMouse/ResizeMouse owns an active GrabPointer.
	// SwapClients checks this to avoid replacing/releasing the outer grab.
	dragging bool

	// Action dispatch table
	Actions map[string]config.ActionFunc

	// Cairo titlebar support
	XlibDpy        unsafe.Pointer // *C.Display – opened once for Cairo
	ShapeAvailable bool
	TitlebarMap    map[xproto.Window]*Client // titlebar win → owning client
	FrameMap       map[xproto.Window]*Client // floating frame win → owning client
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
	NetFrameExtents
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

func (c *Client) rememberFullscreenGeometry() {
	c.FullscreenX = c.X
	c.FullscreenY = c.Y
	c.FullscreenW = c.W
	c.FullscreenH = c.H
	c.FullscreenRestoreValid = true
}

func (c *Client) fullscreenRestoreGeometry() (x, y, width, height int) {
	if c.FullscreenRestoreValid {
		return c.FullscreenX, c.FullscreenY, c.FullscreenW, c.FullscreenH
	}
	return c.OldX, c.OldY, c.OldW, c.OldH
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
