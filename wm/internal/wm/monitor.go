package wm

import (
	"sort"

	"github.com/jezek/xgb/xinerama"
	"github.com/jezek/xgb/xproto"
)

// updateGeom discovers monitors via Xinerama or falls back to root geometry.
func (wm *WM) updateGeom() bool {
	wasXineramaAvailable := wm.XineramaAvailable
	rects := wm.queryMonitorRects()
	if len(rects) == 0 {
		rects = []monitorRect{{0, 0, wm.SW, wm.SH}}
	}
	old := wm.monitorSlice()
	clients := make([]*Client, 0)
	for _, m := range old {
		for c := m.Clients; c != nil; c = c.Next {
			clients = append(clients, c)
		}
	}
	dirty := len(old) != len(rects) || wasXineramaAvailable != wm.XineramaAvailable
	monitors := make([]*Monitor, len(rects))
	for i, rect := range rects {
		if i < len(old) {
			monitors[i] = old[i]
		} else {
			monitors[i] = CreateMon(wm.Layouts)
			dirty = true
		}
		m := monitors[i]
		m.Num = i
		if m.MX != rect.x || m.MY != rect.y || m.MW != rect.w || m.MH != rect.h {
			dirty = true
		}
		m.MX, m.MY, m.MW, m.MH = rect.x, rect.y, rect.w, rect.h
		m.Next = nil
		wm.updateBarPos(m)
		if i > 0 {
			monitors[i-1].Next = m
		}
	}
	wm.Mons = monitors[0]
	if dirty && len(old) > 0 {
		for _, c := range clients {
			target := wm.RectToMon(c.X, c.Y, c.W, c.H)
			if target != nil && target != c.Mon {
				wm.detach(c)
				wm.detachStack(c)
				c.Mon = target
				wm.attachBottom(c)
				wm.attachStack(c)
			}
		}
	}
	if wm.SelMon == nil || !monitorInSlice(wm.SelMon, monitors) {
		wm.SelMon = wm.Mons
	}
	return dirty
}

type monitorRect struct{ x, y, w, h int }

func (wm *WM) queryMonitorRects() []monitorRect {
	if wm.Conn == nil {
		return nil
	}
	if err := xinerama.Init(wm.Conn); err != nil {
		wm.XineramaAvailable = false
		return nil
	}
	active, err := xinerama.IsActive(wm.Conn).Reply()
	if err != nil || active == nil || active.State == 0 {
		wm.XineramaAvailable = false
		return nil
	}
	reply, err := xinerama.QueryScreens(wm.Conn).Reply()
	if err != nil || reply == nil || len(reply.ScreenInfo) == 0 {
		wm.XineramaAvailable = false
		return nil
	}
	wm.XineramaAvailable = true
	seen := make(map[monitorRect]bool)
	rects := make([]monitorRect, 0, len(reply.ScreenInfo))
	for _, screen := range reply.ScreenInfo {
		r := monitorRect{int(screen.XOrg), int(screen.YOrg), int(screen.Width), int(screen.Height)}
		if r.w > 0 && r.h > 0 && !seen[r] {
			seen[r] = true
			rects = append(rects, r)
		}
	}
	// Xinerama normally supplies stable indices. Sorting only makes servers
	// that return an unstable set deterministic from the root's top-left.
	sort.SliceStable(rects, func(i, j int) bool {
		if rects[i].y != rects[j].y {
			return rects[i].y < rects[j].y
		}
		return rects[i].x < rects[j].x
	})
	return rects
}

func monitorInSlice(want *Monitor, monitors []*Monitor) bool {
	for _, m := range monitors {
		if m == want {
			return true
		}
	}
	return false
}

func (wm *WM) updateBarPos(m *Monitor) {
	wm.recomputeWorkArea(m)
}

func (wm *WM) monitorSlice() []*Monitor {
	var monitors []*Monitor
	for m := wm.Mons; m != nil; m = m.Next {
		monitors = append(monitors, m)
	}
	return monitors
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
