package wm

import (
	"github.com/BurntSushi/xgb/xproto"
)

// updateGeom discovers monitors via Xinerama or falls back to root geometry.
func (wm *WM) updateGeom() bool {
	dirty := false

	// Try Xinerama first
	// For simplicity, we'll fall back to single-monitor mode.
	// Xinerama support can be added later with the xinerama xgb extension.
	if wm.Mons == nil {
		wm.Mons = CreateMon(wm.Layouts)
		dirty = true
	}
	if wm.Mons.MW != wm.SW || wm.Mons.MH != wm.SH {
		dirty = true
		wm.Mons.MW = wm.SW
		wm.Mons.WW = wm.SW
		wm.Mons.MH = wm.SH
		wm.Mons.WH = wm.SH
		wm.updateBarPos(wm.Mons)
	}

	if dirty {
		wm.SelMon = wm.Mons
		wm.SelMon = wm.winToMon(wm.Root)
	}
	return dirty
}

func (wm *WM) updateBarPos(m *Monitor) {
	m.WY = m.MY
	m.WH = m.MH
}

// RectToMon returns the monitor with the largest intersection.
func (wm *WM) RectToMon(x, y, w, h int) *Monitor {
	r := wm.SelMon
	area := 0
	for m := wm.Mons; m != nil; m = m.Next {
		a := Intersect(x, y, w, h, m)
		if a > area {
			area = a
			r = m
		}
	}
	return r
}

// winToMon returns the monitor containing the given window.
func (wm *WM) winToMon(w xproto.Window) *Monitor {
	if w == wm.Root {
		x, y := wm.getRootPtr()
		return wm.RectToMon(x, y, 1, 1)
	}

	if c := wm.winToClient(w); c != nil {
		return c.Mon
	}
	return wm.SelMon
}

// DirToMon returns the next/prev monitor in direction dir.
func (wm *WM) DirToMon(dir int) *Monitor {
	if dir > 0 {
		if wm.SelMon.Next != nil {
			return wm.SelMon.Next
		}
		return wm.Mons
	}

	if wm.SelMon == wm.Mons {
		// Go to last monitor
		m := wm.Mons
		for m.Next != nil {
			m = m.Next
		}
		return m
	}

	m := wm.Mons
	for m.Next != wm.SelMon {
		m = m.Next
	}
	return m
}

func (wm *WM) cleanupMon(mon *Monitor) {
	if mon == wm.Mons {
		wm.Mons = wm.Mons.Next
	} else {
		for m := wm.Mons; m != nil; m = m.Next {
			if m.Next == mon {
				m.Next = mon.Next
				break
			}
		}
	}
}

func (wm *WM) getRootPtr() (int, int) {
	reply, err := xproto.QueryPointer(wm.Conn, wm.Root).Reply()
	if err != nil {
		return 0, 0
	}
	return int(reply.RootX), int(reply.RootY)
}
