package wm

import "testing"

func TestOffsetsAreIdempotent(t *testing.T) {
	wm := New()
	wm.Mons = CreateMon(wm.Layouts)
	wm.SelMon = wm.Mons
	wm.Mons.MW = 800
	wm.Mons.MH = 600
	wm.Mons.WW = 800
	wm.Mons.WH = 600

	wm.SetTopOffset(10)
	wm.SetTopOffset(10)
	wm.SetBottomOffset(20)
	wm.SetBottomOffset(20)

	if got, want := wm.Mons.WY, 10; got != want {
		t.Fatalf("WY = %d, want %d", got, want)
	}
	if got, want := wm.Mons.WH, 570; got != want {
		t.Fatalf("WH = %d, want %d", got, want)
	}
}
