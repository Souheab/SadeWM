package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// Tile performs the tiling layout.
func (wm *WM) Tile(m *Monitor) {
	var n int
	for c := wm.NextTiled(m.Clients); c != nil; c = wm.NextTiled(c.Next) {
		n++
	}
	if n == 0 {
		return
	}

	var mw int
	if n > m.NMaster {
		if m.NMaster > 0 {
			mw = int(float32(m.WW) * m.MFact)
		} else {
			mw = 0
		}
	} else {
		mw = m.WW - m.GapPx
	}

	var mx, tx int
	if m.IsRightTiled {
		mx = m.WX + (m.WW - mw)
		tx = m.WX + m.GapPx
	} else {
		mx = m.WX + m.GapPx
		tx = m.WX + mw + m.GapPx
	}

	i := 0
	my := m.GapPx
	ty := m.GapPx
	for c := wm.NextTiled(m.Clients); c != nil; c = wm.NextTiled(c.Next) {
		if c.Maximized {
			wm.Resize(c, m.WX, m.WY, m.WW-2*c.BW, m.WH-2*c.BW, false)
			i++
			continue
		}

		if i < m.NMaster {
			remaining := min(n, m.NMaster) - i
			h := (m.WH-my)/remaining - m.GapPx
			wm.Resize(c, mx, m.WY+my, mw-2*c.BW-m.GapPx, h-2*c.BW, false)
			if my+c.Height()+m.GapPx < m.WH {
				my += c.Height() + m.GapPx
			}
		} else {
			remaining := n - i
			h := (m.WH-ty)/remaining - m.GapPx
			wm.Resize(c, tx, m.WY+ty, m.WW-mw-2*c.BW-2*m.GapPx, h-2*c.BW, false)
			if ty+c.Height()+m.GapPx < m.WH {
				ty += c.Height() + m.GapPx
			}
		}
		i++
	}
}

// Arrange show/hides windows and calls the layout function.
func (wm *WM) Arrange(m *Monitor) {
	if m != nil {
		wm.showHide(m.Stack)
	} else {
		for mon := wm.Mons; mon != nil; mon = mon.Next {
			wm.showHide(mon.Stack)
		}
	}
	if m != nil {
		wm.arrangeMon(m)
		wm.Restack(m)
	} else {
		for mon := wm.Mons; mon != nil; mon = mon.Next {
			wm.arrangeMon(mon)
		}
	}
}

func (wm *WM) arrangeMon(m *Monitor) {
	m.LtSymbol = m.Lt.Symbol
	if m.Lt.Arrange != nil {
		m.Lt.Arrange(m)
	}
}

// Restack manages Z-order of windows.
func (wm *WM) Restack(m *Monitor) {
	if m.Sel == nil {
		return
	}

	if m.Sel.IsFloating || m.Sel.IsAbove || m.Lt.Arrange == nil {
		wm.raiseWindow(m.Sel.Win)
	}

	if m.Lt.Arrange != nil {
		// Stack tiled windows below each other.  Dwm uses the bar
		// window as the initial sibling, but sadewm has no bar window
		// (sadeshell is a separate process), so we simply lower each
		// tiled window and chain siblings.
		var sibling xproto.Window
		for c := m.Stack; c != nil; c = c.SNext {
			if !c.IsFloating && !c.IsAbove && c.IsVisible() {
				if sibling != 0 {
					xproto.ConfigureWindow(wm.Conn, c.Win,
						xproto.ConfigWindowSibling|xproto.ConfigWindowStackMode,
						[]uint32{uint32(sibling), uint32(xproto.StackModeBelow)})
				} else {
					xproto.ConfigureWindow(wm.Conn, c.Win,
						xproto.ConfigWindowStackMode,
						[]uint32{uint32(xproto.StackModeBelow)})
				}
				sibling = c.Win
			}
		}
	}

	// Raise all floating/above windows
	for c := m.Stack; c != nil; c = c.SNext {
		if c.IsVisible() && (c.IsFloating || c.IsAbove) {
			wm.raiseWindow(c.Win)
			wm.raiseTitlebar(c)
		}
	}
}

func (wm *WM) raiseWindow(win xproto.Window) {
	xproto.ConfigureWindow(wm.Conn, win,
		xproto.ConfigWindowStackMode,
		[]uint32{uint32(xproto.StackModeAbove)})
}

func (wm *WM) showHide(c *Client) {
	if c == nil {
		return
	}
	if c.IsVisible() {
		xproto.ConfigureWindow(wm.Conn, c.Win,
			xproto.ConfigWindowX|xproto.ConfigWindowY,
			[]uint32{uint32(c.X), uint32(c.Y)})
		if (c.Mon.Lt.Arrange == nil || c.IsFloating) && !c.IsFullscreen {
			wm.Resize(c, c.X, c.Y, c.W, c.H, false)
		}
		wm.showTitlebar(c)
		wm.showHide(c.SNext)
	} else {
		wm.showHide(c.SNext)
		xproto.ConfigureWindow(wm.Conn, c.Win,
			xproto.ConfigWindowX,
			[]uint32{uint32(c.Width() * -2)})
		wm.hideTitlebar(c)
	}
}

// Resize applies size hint checks and resizes a client.
func (wm *WM) Resize(c *Client, x, y, w, h int, interact bool) {
	if wm.applySizeHints(c, &x, &y, &w, &h, interact) {
		wm.resizeClient(c, x, y, w, h)
	}
}

func (wm *WM) resizeClient(c *Client, x, y, w, h int) {
	c.OldX = c.X
	c.OldY = c.Y
	c.OldW = c.W
	c.OldH = c.H
	c.X = x
	c.Y = y
	c.W = w
	c.H = h

	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowX|xproto.ConfigWindowY|
			xproto.ConfigWindowWidth|xproto.ConfigWindowHeight|
			xproto.ConfigWindowBorderWidth,
		[]uint32{uint32(x), uint32(y), uint32(w), uint32(h), uint32(c.BW)})
	wm.configure(c)
	wm.moveTitlebar(c)
}

func (wm *WM) configure(c *Client) {
	event := xproto.ConfigureNotifyEvent{
		Event:            c.Win,
		Window:           c.Win,
		X:                int16(c.X),
		Y:                int16(c.Y),
		Width:            uint16(c.W),
		Height:           uint16(c.H),
		BorderWidth:      uint16(c.BW),
		AboveSibling:     xproto.WindowNone,
		OverrideRedirect: false,
	}
	xproto.SendEvent(wm.Conn, false, c.Win, xproto.EventMaskStructureNotify, string(event.Bytes()))
}

// NextTiled returns the next tiled (non-floating, visible) client.
func (wm *WM) NextTiled(c *Client) *Client {
	for ; c != nil; c = c.Next {
		if !c.IsFloating && c.IsVisible() {
			return c
		}
	}
	return nil
}

func (wm *WM) onlyClient(c *Client) bool {
	return (c.H+2*int(config.BorderPx)+2*int(config.GapPx)) >= wm.SelMon.WH &&
		(c.W+2*int(config.BorderPx)+2*int(config.GapPx)) >= wm.SelMon.WW
}

func (wm *WM) applySizeHints(c *Client, x, y, w, h *int, interact bool) bool {
	*w = max(1, *w)
	*h = max(1, *h)

	if interact {
		if *x > wm.SW {
			*x = wm.SW - c.Width()
		}
		if *y > wm.SH {
			*y = wm.SH - c.Height()
		}
		if *x+*w+2*c.BW < 0 {
			*x = 0
		}
		if *y+*h+2*c.BW < 0 {
			*y = 0
		}
	} else {
		m := c.Mon
		if *x >= m.WX+m.WW {
			*x = m.WX + m.WW - c.Width()
		}
		if *y >= m.WY+m.WH {
			*y = m.WY + m.WH - c.Height()
		}
		if *x+*w+2*c.BW <= m.WX {
			*x = m.WX
		}
		if *y+*h+2*c.BW <= m.WY {
			*y = m.WY
		}
	}

	if *h < 3 {
		*h = 3
	}
	if *w < 3 {
		*w = 3
	}

	if wm.honorSizeHints(c) && (config.ResizeHints || c.IsFloating || c.Mon.Lt.Arrange == nil) {
		if !c.HintsValid {
			wm.updateSizeHints(c)
		}
		baseIsMin := c.BaseW == c.MinW && c.BaseH == c.MinH
		if !baseIsMin {
			*w -= c.BaseW
			*h -= c.BaseH
		}
		if c.MinA > 0 && c.MaxA > 0 {
			if c.MaxA < float32(*w)/float32(*h) {
				*w = int(float32(*h)*c.MaxA + 0.5)
			} else if c.MinA < float32(*h)/float32(*w) {
				*h = int(float32(*w)*c.MinA + 0.5)
			}
		}
		if baseIsMin {
			*w -= c.BaseW
			*h -= c.BaseH
		}
		if c.IncW > 0 {
			*w -= *w % c.IncW
		}
		if c.IncH > 0 {
			*h -= *h % c.IncH
		}
		*w = max(*w+c.BaseW, c.MinW)
		*h = max(*h+c.BaseH, c.MinH)
		if c.MaxW > 0 {
			*w = min(*w, c.MaxW)
		}
		if c.MaxH > 0 {
			*h = min(*h, c.MaxH)
		}
	}

	return *x != c.X || *y != c.Y || *w != c.W || *h != c.H
}

func (wm *WM) honorSizeHints(c *Client) bool {
	if len(config.SizeHintsWhitelist) == 0 {
		return false
	}

	classReply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmClass, xproto.AtomString, 0, 256).Reply()
	if err != nil || classReply.ValueLen == 0 {
		return false
	}

	parts := splitWMClass(classReply.Value)
	for _, allowed := range config.SizeHintsWhitelist {
		for _, part := range parts {
			if part == allowed {
				return true
			}
		}
	}
	return false
}

func splitWMClass(data []byte) []string {
	var parts []string
	var current []byte
	for _, b := range data {
		if b == 0 {
			if len(current) > 0 {
				parts = append(parts, string(current))
				current = nil
			}
		} else {
			current = append(current, b)
		}
	}
	if len(current) > 0 {
		parts = append(parts, string(current))
	}
	return parts
}

func init() {
	_ = util.LogDebug // ensure import
}
