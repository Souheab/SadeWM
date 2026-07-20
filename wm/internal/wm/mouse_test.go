package wm

import (
	"testing"

	"github.com/jezek/xgb/xproto"
)

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
