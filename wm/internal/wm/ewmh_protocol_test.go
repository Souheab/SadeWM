package wm

import (
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jezek/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
)

func TestEWMHMatrixCoversRegistry(t *testing.T) {
	doc, err := os.ReadFile("../../docs/ewmh-1.5.md")
	if err != nil {
		t.Fatal(err)
	}
	const marker = "The unconditional `_NET_SUPPORTED` inventory is:\n\n```text\n"
	start := strings.Index(string(doc), marker)
	if start < 0 {
		t.Fatal("compliance matrix is missing its generated registry inventory")
	}
	inventory := string(doc)[start+len(marker):]
	end := strings.Index(inventory, "\n```")
	if end < 0 {
		t.Fatal("compliance matrix registry inventory is not terminated")
	}
	lines := strings.Fields(inventory[:end])
	if len(lines) != len(supportedAtomNames) {
		t.Fatalf("matrix has %d unconditional atoms, registry has %d", len(lines), len(supportedAtomNames))
	}
	for i, name := range supportedAtomNames {
		if lines[i] != string(name) {
			t.Errorf("matrix atom %d = %s, registry has %s", i, lines[i], name)
		}
	}
}

func TestSupportedAtomRegistryDoesNotOverclaim(t *testing.T) {
	seen := make(map[AtomName]bool)
	for _, name := range supportedAtomNames {
		if seen[name] {
			t.Fatalf("duplicate supported atom %s", name)
		}
		seen[name] = true
	}
	for _, name := range []AtomName{NetSupported, NetClientList, NetClientListStacking,
		NetCurrentDesktop, NetActiveWindow, NetWorkarea, NetWMState, NetWMAllowedActions,
		NetWMWindowType, NetWMPing} {
		if !seen[name] {
			t.Errorf("required implemented atom %s is not advertised", name)
		}
	}
	for _, name := range []AtomName{NetWMStateStaysOnTop, NetWMSyncRequest,
		NetWMSyncRequestCounter, NetWMFullscreenMonitors, NetWMWindowOpacity} {
		if seen[name] {
			t.Errorf("conditional/legacy atom %s must not be in the unconditional registry", name)
		}
	}
}

func TestRequestedState(t *testing.T) {
	tests := []struct {
		name    string
		action  uint32
		current bool
		want    bool
		valid   bool
	}{
		{"remove", netWMStateRemove, true, false, true},
		{"add", netWMStateAdd, false, true, true},
		{"toggle-on", netWMStateToggle, false, true, true},
		{"toggle-off", netWMStateToggle, true, false, true},
		{"invalid", 99, true, true, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, valid := requestedState(tt.action, tt.current)
			if got != tt.want || valid != tt.valid {
				t.Fatalf("requestedState(%d, %v) = (%v, %v), want (%v, %v)",
					tt.action, tt.current, got, valid, tt.want, tt.valid)
			}
		})
	}
}

func TestDesktopTagMappingIsCanonicalAndLossy(t *testing.T) {
	last := uint32(len(config.Tags) - 1)
	tests := []struct {
		tags uint32
		want uint32
	}{
		{1, 0},
		{0b101, 2},
		{1 << last, last},
		{TagMask(), ^uint32(0)},
	}
	for _, tt := range tests {
		if got := desktopForTags(tt.tags); got != tt.want {
			t.Errorf("desktopForTags(%#x) = %#x, want %#x", tt.tags, got, tt.want)
		}
	}
}

func TestXTimestampComparisonWraparound(t *testing.T) {
	tests := []struct {
		value, reference uint32
		want             bool
	}{
		{100, 100, true},
		{101, 100, true},
		{99, 100, false},
		{2, ^uint32(0) - 2, true},
		{^uint32(0) - 2, 2, false},
	}
	for _, tt := range tests {
		if got := xTimeNotBefore(tt.value, tt.reference); got != tt.want {
			t.Errorf("xTimeNotBefore(%d, %d) = %v, want %v", tt.value, tt.reference, got, tt.want)
		}
	}
}

func TestGravityDecorationOffset(t *testing.T) {
	tests := []struct {
		gravity byte
		x, y    int
	}{
		{1, 3, 28},   // NorthWest
		{5, 1, 12},   // Center
		{9, -1, -4},  // SouthEast
		{10, -1, -4}, // Static
	}
	for _, tt := range tests {
		x, y := gravityDecorationOffset(tt.gravity, 3, 1, 28, 4)
		if x != tt.x || y != tt.y {
			t.Errorf("gravity %d offset = %d,%d, want %d,%d", tt.gravity, x, y, tt.x, tt.y)
		}
	}
}

func TestMoveResizeGeometryAllEdgesAndRollbackBasis(t *testing.T) {
	tests := []struct {
		direction uint32
		want      [4]int
	}{
		{0, [4]int{110, 220, 290, 180}},
		{1, [4]int{100, 220, 300, 180}},
		{2, [4]int{100, 220, 310, 180}},
		{3, [4]int{100, 200, 310, 200}},
		{4, [4]int{100, 200, 310, 220}},
		{5, [4]int{100, 200, 300, 220}},
		{6, [4]int{110, 200, 290, 220}},
		{7, [4]int{110, 200, 290, 200}},
		{8, [4]int{110, 220, 300, 200}},
	}
	for _, tt := range tests {
		x, y, width, height := moveResizeGeometry(100, 200, 300, 200, 10, 20, tt.direction)
		got := [4]int{x, y, width, height}
		if got != tt.want {
			t.Errorf("direction %d geometry = %v, want %v", tt.direction, got, tt.want)
		}
	}
}

func TestLayerOrdering(t *testing.T) {
	m := &Monitor{}
	wm := &WM{SelMon: m}
	normal := &Client{Mon: m}
	m.Sel = normal
	tests := []struct {
		client *Client
		want   int
	}{
		{&Client{Mon: m, IsDesktop: true}, 0},
		{&Client{Mon: m, IsBelow: true}, 1},
		{normal, 2},
		{&Client{Mon: m, IsDock: true}, 3},
		{&Client{Mon: m, IsDock: true, IsBelow: true}, 3},
		{&Client{Mon: m, IsAbove: true}, 3},
	}
	for _, tt := range tests {
		if got := wm.clientLayer(tt.client); got != tt.want {
			t.Errorf("client layer = %d, want %d for %+v", got, tt.want, tt.client)
		}
	}
	normal.IsFullscreen = true
	if got := wm.clientLayer(normal); got != 4 {
		t.Errorf("focused fullscreen layer = %d, want 4", got)
	}
}

func TestMonitorIntersectionUsesPhysicalGeometry(t *testing.T) {
	m := &Monitor{MX: 0, MY: 0, MW: 100, MH: 100, WX: 20, WY: 20, WW: 60, WH: 60}
	if got := Intersect(0, 0, 10, 10, m); got != 100 {
		t.Fatalf("physical intersection = %d, want 100", got)
	}
}

func TestShowingDesktopVisibility(t *testing.T) {
	m := &Monitor{SelTags: 0, TagSet: [2]uint32{1, 1}}
	ordinary := &Client{Mon: m, Tags: 1}
	dock := &Client{Mon: m, Tags: TagMask(), IsDock: true}
	wm := &WM{ShowingDesktop: true}
	if wm.clientVisible(ordinary) {
		t.Fatal("ordinary client remained visible while showing the desktop")
	}
	if !wm.clientVisible(dock) {
		t.Fatal("dock was hidden while showing the desktop")
	}
}

func TestPartialStrutOnlyAffectsIntersectingMonitor(t *testing.T) {
	left := &Monitor{MX: 0, MY: 0, MW: 960, MH: 1080}
	right := &Monitor{MX: 960, MY: 0, MW: 960, MH: 1080}
	strut := [12]uint32{2: 60, 8: 0, 9: 959}
	wm := &WM{SW: 1920, SH: 1080, TopOffset: 40,
		DockStruts: map[xproto.Window][12]uint32{1: strut}}
	wm.applyMonitorStruts(left)
	wm.applyMonitorStruts(right)
	if left.WY != 60 || left.WH != 1020 {
		t.Errorf("left workarea y/height = %d/%d, want 60/1020", left.WY, left.WH)
	}
	if right.WY != 40 || right.WH != 1040 {
		t.Errorf("right workarea y/height = %d/%d, want 40/1040", right.WY, right.WH)
	}
}

func TestFullscreenBounds(t *testing.T) {
	monitors := []*Monitor{
		{MX: 0, MY: 0, MW: 1920, MH: 1080},
		{MX: 1920, MY: 0, MW: 1920, MH: 1080},
	}
	x, y, width, height, ok := fullscreenBounds(monitors, [4]uint32{0, 1, 0, 1})
	if !ok || x != 0 || y != 0 || width != 3840 || height != 1080 {
		t.Fatalf("fullscreen bounds = %d,%d %dx%d ok=%v", x, y, width, height, ok)
	}
	if _, _, _, _, ok := fullscreenBounds(monitors, [4]uint32{0, 2, 0, 1}); ok {
		t.Fatal("out-of-range fullscreen monitor index was accepted")
	}
}

func TestXSyncThrottleFallsBackAfterOneSecond(t *testing.T) {
	c := &Client{SyncWaiting: true, SyncDeadline: time.Now().Add(-time.Millisecond)}
	m := &Monitor{Clients: c}
	c.Mon = m
	wm := &WM{Mons: m}
	wm.checkProtocolTimeouts(time.Now())
	if c.SyncWaiting {
		t.Fatal("expired XSync resize did not fall back")
	}
}

func TestXSyncValueEncoding(t *testing.T) {
	want := uint64(0xfedcba9876543210)
	low, high := splitXSyncValue(want)
	if got := joinXSyncValue(low, high); got != want {
		t.Fatalf("XSync value round trip = %#x, want %#x", got, want)
	}
}

func TestMalformedStrutsAreClampedToRoot(t *testing.T) {
	m := &Monitor{MX: 0, MY: 0, MW: 800, MH: 600}
	wm := &WM{SW: 800, SH: 600, Mons: m,
		DockStruts: map[xproto.Window][12]uint32{1: {0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff}}}
	wm.publishWorkareaFromStruts()
	if m.WW < 1 || m.WH < 1 || m.WX < 0 || m.WY < 0 {
		t.Fatalf("invalid clamped workarea: %d,%d %dx%d", m.WX, m.WY, m.WW, m.WH)
	}
}
