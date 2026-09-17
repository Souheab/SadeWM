package wm

import (
	"testing"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
)

func TestDragPositionAppliesReleaseAndPreservesEvents(t *testing.T) {
	wm := New()
	wm.XEvCh = make(chan xgbEvent, 8)
	configure := xproto.ConfigureRequestEvent{Window: 17}
	property := xproto.PropertyNotifyEvent{Window: 18}
	for _, ev := range []xgb.Event{
		configure, xproto.MotionNotifyEvent{RootX: 40, RootY: 50}, property,
		xproto.ButtonReleaseEvent{RootX: 70, RootY: 80, Time: 99},
		xproto.MotionNotifyEvent{RootX: 100, RootY: 110},
	} {
		wm.XEvCh <- xgbEvent{ev: ev}
	}
	motion, released := wm.dragPosition(xproto.MotionNotifyEvent{RootX: 10, RootY: 20})
	if !released || motion.RootX != 70 || motion.RootY != 80 || motion.Time != 99 {
		t.Fatalf("lost release coordinates: %+v, released=%v", motion, released)
	}
	if len(wm.pendingEvts) != 2 || wm.pendingEvts[0] != configure || wm.pendingEvts[1] != property {
		t.Fatalf("lost/reordered deferred events: %+v", wm.pendingEvts)
	}
	if len(wm.XEvCh) != 1 {
		t.Fatal("consumed events after the release")
	}
}

func TestDragPositionWithoutQueuedMotion(t *testing.T) {
	wm := New()
	wm.XEvCh = make(chan xgbEvent, 1)
	motion, released := wm.dragPosition(xproto.MotionNotifyEvent{RootX: 10, RootY: 20})
	if released || motion.RootX != 10 || motion.RootY != 20 {
		t.Fatal("changed a standalone motion")
	}
	motion, released = wm.dragPosition(xproto.ButtonReleaseEvent{RootX: 30, RootY: 40})
	if !released || motion.RootX != 30 || motion.RootY != 40 {
		t.Fatal("lost standalone release coordinates")
	}
}

func TestSnapClientYKeepsDecoratedFrameBelowWorkArea(t *testing.T) {
	wm := New()
	wm.SelMon = &Monitor{WY: 40, WH: 600}
	c := &Client{Y: 100, W: 400, H: 300, FrameWin: xproto.Window(1)}

	got := wm.snapClientY(c, 20, c.Y)
	want := wm.SelMon.WY + titlebarHeight
	if got != want {
		t.Fatalf("content Y = %d, want %d so titlebar top is at work-area Y", got, want)
	}
}

func TestSnapClientYLeavesUndecoratedTopEdgeAtWorkArea(t *testing.T) {
	wm := New()
	wm.SelMon = &Monitor{WY: 40, WH: 600}
	c := &Client{Y: 100, W: 400, H: 300}

	got := wm.snapClientY(c, 20, c.Y)
	want := wm.SelMon.WY
	if got != want {
		t.Fatalf("content Y = %d, want %d for undecorated client", got, want)
	}
}

func TestSnapClientYUsesDecoratedFrameForBottomEdge(t *testing.T) {
	wm := New()
	wm.SelMon = &Monitor{WY: 40, WH: 600}
	c := &Client{Y: 100, W: 400, H: 300, FrameWin: xproto.Window(1)}

	got := wm.snapClientY(c, 500, c.Y)
	want := wm.SelMon.WY + wm.SelMon.WH - c.Height()
	if got != want {
		t.Fatalf("content Y = %d, want %d so frame bottom is at work-area bottom", got, want)
	}
}
