package wm

import (
	"testing"

	"github.com/sadewm/sadewm/wm/internal/config"
)

func TestPlaceFloatingOnManageCentersWindow(t *testing.T) {
	old := config.CenterFloating
	config.CenterFloating = true
	t.Cleanup(func() {
		config.CenterFloating = old
	})

	wm := New()
	mon := &Monitor{WX: 100, WY: 50, WW: 800, WH: 600}
	c := &Client{Mon: mon, X: 0, Y: 0, W: 200, H: 100, IsFloating: true}

	wm.placeFloatingOnManage(c)

	if got, want := c.X, 400; got != want {
		t.Fatalf("X = %d, want %d", got, want)
	}
	if got, want := c.Y, 314; got != want {
		t.Fatalf("Y = %d, want %d", got, want)
	}
}

func TestPlaceFloatingOnManageHonorsPositionHint(t *testing.T) {
	old := config.CenterFloating
	config.CenterFloating = true
	t.Cleanup(func() {
		config.CenterFloating = old
	})

	wm := New()
	mon := &Monitor{WX: 100, WY: 50, WW: 800, WH: 600}
	c := &Client{
		Mon:             mon,
		X:               123,
		Y:               234,
		W:               200,
		H:               100,
		IsFloating:      true,
		HasPositionHint: true,
	}

	wm.placeFloatingOnManage(c)

	if got, want := c.X, 123; got != want {
		t.Fatalf("X = %d, want %d", got, want)
	}
	if got, want := c.Y, 234; got != want {
		t.Fatalf("Y = %d, want %d", got, want)
	}
}

func TestPlaceFloatingOnManageLeavesNonFloatingDockAndFullscreen(t *testing.T) {
	old := config.CenterFloating
	config.CenterFloating = true
	t.Cleanup(func() {
		config.CenterFloating = old
	})

	wm := New()
	mon := &Monitor{WX: 0, WY: 0, WW: 800, WH: 600}
	tests := []struct {
		name string
		c    Client
	}{
		{name: "tiled", c: Client{Mon: mon, X: 10, Y: 20, W: 200, H: 100}},
		{name: "dock", c: Client{Mon: mon, X: 10, Y: 20, W: 200, H: 100, IsFloating: true, IsDock: true}},
		{name: "fullscreen", c: Client{Mon: mon, X: 10, Y: 20, W: 200, H: 100, IsFloating: true, IsFullscreen: true}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := tt.c
			wm.placeFloatingOnManage(&c)
			if got, want := c.X, tt.c.X; got != want {
				t.Fatalf("X = %d, want %d", got, want)
			}
			if got, want := c.Y, tt.c.Y; got != want {
				t.Fatalf("Y = %d, want %d", got, want)
			}
		})
	}
}

func TestPlaceFloatingOnManageClampsOversizedWindow(t *testing.T) {
	old := config.CenterFloating
	config.CenterFloating = true
	t.Cleanup(func() {
		config.CenterFloating = old
	})

	wm := New()
	mon := &Monitor{WX: 50, WY: 40, WW: 300, WH: 200}
	c := &Client{Mon: mon, X: 0, Y: 0, W: 500, H: 300, IsFloating: true}

	wm.placeFloatingOnManage(c)

	if got, want := c.X, 50; got != want {
		t.Fatalf("X = %d, want %d", got, want)
	}
	if got, want := c.Y, 68; got != want {
		t.Fatalf("Y = %d, want %d", got, want)
	}
}
