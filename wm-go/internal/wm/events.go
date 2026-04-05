package wm

import (
	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/xproto"
	"github.com/BurntSushi/xgbutil/keybind"

	"github.com/sadewm/sadewm/wm-go/internal/config"
)

func (wm *WM) handleEvent(ev xgb.Event) {
	switch e := ev.(type) {
	case xproto.ButtonPressEvent:
		wm.handleButtonPress(e)
	case xproto.ClientMessageEvent:
		wm.handleClientMessage(e)
	case xproto.ConfigureRequestEvent:
		wm.handleConfigureRequest(e)
	case xproto.ConfigureNotifyEvent:
		wm.handleConfigureNotify(e)
	case xproto.DestroyNotifyEvent:
		wm.handleDestroyNotify(e)
	case xproto.EnterNotifyEvent:
		wm.handleEnterNotify(e)
	case xproto.FocusInEvent:
		wm.handleFocusIn(e)
	case xproto.KeyPressEvent:
		wm.handleKeyPress(e)
	case xproto.MappingNotifyEvent:
		wm.handleMappingNotify(e)
	case xproto.MapRequestEvent:
		wm.handleMapRequest(e)
	case xproto.MotionNotifyEvent:
		wm.handleMotionNotify(e)
	case xproto.PropertyNotifyEvent:
		wm.handlePropertyNotify(e)
	case xproto.UnmapNotifyEvent:
		wm.handleUnmapNotify(e)
	}
}

func (wm *WM) handleButtonPress(e xproto.ButtonPressEvent) {
	click := config.ClkRootWin

	if m := wm.winToMon(e.Event); m != nil && m != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = m
		wm.Focus(nil)
	}

	if c := wm.winToClient(e.Event); c != nil {
		wm.Focus(c)
		wm.Restack(wm.SelMon)
		xproto.AllowEvents(wm.Conn, xproto.AllowReplayPointer, xproto.TimeCurrentTime)
		click = config.ClkClientWin
	}

	buttons := config.DefaultButtons()
	for _, btn := range buttons {
		if click == btn.Click && btn.Button == xproto.Button(e.Detail) &&
			wm.cleanMask(btn.Mask) == wm.cleanMask(e.State) {
			if action, ok := wm.Actions[btn.Action]; ok {
				action(&btn.Arg)
			}
		}
	}
}

func (wm *WM) handleClientMessage(e xproto.ClientMessageEvent) {
	c := wm.winToClient(e.Window)
	if c == nil {
		return
	}

	if e.Type == wm.NetAtom[NetWMState] {
		d := e.Data.Data32
		if xproto.Atom(d[1]) == wm.NetAtom[NetWMFullscreen] || xproto.Atom(d[2]) == wm.NetAtom[NetWMFullscreen] {
			wm.SetFullscreen(c, d[0] == 1 || (d[0] == 2 && !c.IsFullscreen))
		}
		if xproto.Atom(d[1]) == wm.NetAtom[NetWMStateAbove] || xproto.Atom(d[2]) == wm.NetAtom[NetWMStateAbove] ||
			xproto.Atom(d[1]) == wm.NetAtom[NetWMStateStaysOnTop] || xproto.Atom(d[2]) == wm.NetAtom[NetWMStateStaysOnTop] {
			wm.SetAbove(c, d[0] == 1 || (d[0] == 2 && !c.IsAbove))
		}
	} else if e.Type == wm.NetAtom[NetActiveWindow] {
		if c != wm.SelMon.Sel && !c.IsUrgent {
			wm.setUrgent(c, true)
		}
	}
}

func (wm *WM) handleConfigureRequest(e xproto.ConfigureRequestEvent) {
	c := wm.winToClient(e.Window)
	if c != nil {
		if c.IsDock {
			return
		}
		if e.ValueMask&xproto.ConfigWindowBorderWidth != 0 {
			c.BW = int(e.BorderWidth)
		} else if c.IsFloating || wm.SelMon.Lt.Arrange == nil {
			m := c.Mon
			if e.ValueMask&xproto.ConfigWindowX != 0 {
				c.OldX = c.X
				c.X = m.MX + int(e.X)
			}
			if e.ValueMask&xproto.ConfigWindowY != 0 {
				c.OldY = c.Y
				c.Y = m.MY + int(e.Y)
			}
			if e.ValueMask&xproto.ConfigWindowWidth != 0 {
				c.OldW = c.W
				c.W = int(e.Width)
			}
			if e.ValueMask&xproto.ConfigWindowHeight != 0 {
				c.OldH = c.H
				c.H = int(e.Height)
			}
			if (c.X+c.W) > m.MX+m.MW && c.IsFloating {
				c.X = m.MX + (m.MW/2 - c.Width()/2)
			}
			if (c.Y+c.H) > m.MY+m.MH && c.IsFloating {
				c.Y = m.MY + (m.MH/2 - c.Height()/2)
			}
			if (e.ValueMask&(xproto.ConfigWindowX|xproto.ConfigWindowY)) != 0 &&
				(e.ValueMask&(xproto.ConfigWindowWidth|xproto.ConfigWindowHeight)) == 0 {
				wm.configure(c)
			}
			if c.IsVisible() {
				xproto.ConfigureWindow(wm.Conn, c.Win,
					xproto.ConfigWindowX|xproto.ConfigWindowY|
						xproto.ConfigWindowWidth|xproto.ConfigWindowHeight,
					[]uint32{uint32(c.X), uint32(c.Y), uint32(c.W), uint32(c.H)})
			}
		} else {
			wm.configure(c)
		}
	} else {
		values := []uint32{}
		mask := uint16(0)
		if e.ValueMask&xproto.ConfigWindowX != 0 {
			values = append(values, uint32(e.X))
			mask |= xproto.ConfigWindowX
		}
		if e.ValueMask&xproto.ConfigWindowY != 0 {
			values = append(values, uint32(e.Y))
			mask |= xproto.ConfigWindowY
		}
		if e.ValueMask&xproto.ConfigWindowWidth != 0 {
			values = append(values, uint32(e.Width))
			mask |= xproto.ConfigWindowWidth
		}
		if e.ValueMask&xproto.ConfigWindowHeight != 0 {
			values = append(values, uint32(e.Height))
			mask |= xproto.ConfigWindowHeight
		}
		if e.ValueMask&xproto.ConfigWindowBorderWidth != 0 {
			values = append(values, uint32(e.BorderWidth))
			mask |= xproto.ConfigWindowBorderWidth
		}
		if e.ValueMask&xproto.ConfigWindowSibling != 0 {
			values = append(values, uint32(e.Sibling))
			mask |= xproto.ConfigWindowSibling
		}
		if e.ValueMask&xproto.ConfigWindowStackMode != 0 {
			values = append(values, uint32(e.StackMode))
			mask |= xproto.ConfigWindowStackMode
		}
		xproto.ConfigureWindow(wm.Conn, e.Window, mask, values)
	}
	wm.Conn.Sync()
}

func (wm *WM) handleConfigureNotify(e xproto.ConfigureNotifyEvent) {
	if e.Window != wm.Root {
		return
	}

	dirty := wm.SW != int(e.Width) || wm.SH != int(e.Height)
	wm.SW = int(e.Width)
	wm.SH = int(e.Height)

	if wm.updateGeom() || dirty {
		for m := wm.Mons; m != nil; m = m.Next {
			for c := m.Clients; c != nil; c = c.Next {
				if c.IsFullscreen {
					wm.resizeClient(c, m.MX, m.MY, m.MW, m.MH)
				}
			}
		}
		wm.Focus(nil)
		wm.Arrange(nil)
	}
}

func (wm *WM) handleDestroyNotify(e xproto.DestroyNotifyEvent) {
	if c := wm.winToClient(e.Window); c != nil {
		wm.unmanage(c, true)
	}
}

func (wm *WM) handleEnterNotify(e xproto.EnterNotifyEvent) {
	if (e.Mode != xproto.NotifyModeNormal || e.Detail == xproto.NotifyDetailInferior) && e.Event != wm.Root {
		return
	}

	c := wm.winToClient(e.Event)
	var m *Monitor
	if c != nil {
		m = c.Mon
	} else {
		m = wm.winToMon(e.Event)
	}

	if m != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = m
	} else if c == nil || c == wm.SelMon.Sel {
		return
	}
	wm.Focus(c)
}

func (wm *WM) handleFocusIn(e xproto.FocusInEvent) {
	if wm.SelMon.Sel != nil && e.Event != wm.SelMon.Sel.Win {
		wm.setFocus(wm.SelMon.Sel)
	}
}

func (wm *WM) handleKeyPress(e xproto.KeyPressEvent) {
	for _, key := range wm.ActiveKeys {
		codes := keybind.StrToKeycodes(wm.X, key.KeyStr)
		for _, code := range codes {
			if code == e.Detail && wm.cleanMask(key.Mod) == wm.cleanMask(e.State) {
				if action, ok := wm.Actions[key.Action]; ok {
					action(&key.Arg)
				}
				return
			}
		}
	}
}

func (wm *WM) handleMappingNotify(e xproto.MappingNotifyEvent) {
	if e.Request == xproto.MappingKeyboard {
		keybind.Initialize(wm.X)
		wm.GrabKeys()
	}
}

func (wm *WM) handleMapRequest(e xproto.MapRequestEvent) {
	attrs, err := xproto.GetWindowAttributes(wm.Conn, e.Window).Reply()
	if err != nil || attrs.OverrideRedirect {
		return
	}
	if wm.winToClient(e.Window) == nil {
		wm.manage(e.Window, attrs)
	}
}

func (wm *WM) handleMotionNotify(e xproto.MotionNotifyEvent) {
	if e.Event != wm.Root {
		return
	}
	m := wm.RectToMon(int(e.RootX), int(e.RootY), 1, 1)
	if m != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = m
		wm.Focus(nil)
	}
}

func (wm *WM) handlePropertyNotify(e xproto.PropertyNotifyEvent) {
	if e.State == xproto.PropertyDelete {
		return
	}

	c := wm.winToClient(e.Window)
	if c == nil {
		return
	}

	switch e.Atom {
	case xproto.AtomWmTransientFor:
		prop, err := xproto.GetProperty(wm.Conn, false, c.Win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		if err == nil && prop.ValueLen > 0 && !c.IsFloating {
			if wm.winToClient(xproto.Window(getUint32(prop.Value))) != nil {
				c.IsFloating = true
				wm.Arrange(c.Mon)
			}
		}
	case xproto.AtomWmNormalHints:
		c.HintsValid = false
	case xproto.AtomWmHints:
		wm.updateWMHints(c)
	}

	if e.Atom == xproto.AtomWmName || e.Atom == wm.NetAtom[NetWMName] {
		wm.updateTitle(c)
	}
	if e.Atom == wm.NetAtom[NetWMWindowType] {
		wm.updateWindowType(c)
	}
}

func (wm *WM) handleUnmapNotify(e xproto.UnmapNotifyEvent) {
	c := wm.winToClient(e.Window)
	if c == nil {
		return
	}
	if e.Event == wm.Root {
		// send_event case — set withdrawn
		wm.setClientState(c, icccmWithdrawnState)
	} else {
		wm.unmanage(c, false)
	}
}

// manage creates a Client for a newly-mapped window.
func (wm *WM) manage(w xproto.Window, wa *xproto.GetWindowAttributesReply) {
	// Check if this is a dock window
	prop, err := xproto.GetProperty(wm.Conn, false, w,
		wm.NetAtom[NetWMWindowType], xproto.AtomAtom, 0, 1).Reply()
	if err == nil && prop.ValueLen > 0 {
		wtype := xproto.Atom(getUint32(prop.Value))
		if wtype == wm.NetAtom[NetWMWindowTypeDock] {
			// Check if it's ABOVE
			isAbove := false
			sp, err := xproto.GetProperty(wm.Conn, false, w,
				wm.NetAtom[NetWMState], xproto.AtomAtom, 0, 1).Reply()
			if err == nil && sp.ValueLen > 0 {
				s := xproto.Atom(getUint32(sp.Value))
				if s == wm.NetAtom[NetWMStateAbove] || s == wm.NetAtom[NetWMStateStaysOnTop] {
					isAbove = true
				}
			}
			if !isAbove {
				xproto.MapWindow(wm.Conn, w)
				return
			}
		}
	}

	// Get geometry
	geom, err := xproto.GetGeometry(wm.Conn, xproto.Drawable(w)).Reply()
	if err != nil {
		return
	}

	c := &Client{
		Win:  w,
		X:    int(geom.X),
		Y:    int(geom.Y),
		W:    int(geom.Width),
		H:    int(geom.Height),
		OldX: int(geom.X),
		OldY: int(geom.Y),
		OldW: int(geom.Width),
		OldH: int(geom.Height),
		OldBW: int(geom.BorderWidth),
	}

	wm.updateTitle(c)

	// Check transient
	transProp, err := xproto.GetProperty(wm.Conn, false, w,
		xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
	if err == nil && transProp.ValueLen > 0 {
		transWin := xproto.Window(getUint32(transProp.Value))
		if t := wm.winToClient(transWin); t != nil {
			c.Mon = t.Mon
			c.Tags = t.Tags
		}
	}
	if c.Mon == nil {
		c.Mon = wm.SelMon
		wm.applyRules(c)
	}

	// Check dock override
	prop, err = xproto.GetProperty(wm.Conn, false, w,
		wm.NetAtom[NetWMWindowType], xproto.AtomAtom, 0, 1).Reply()
	if err == nil && prop.ValueLen > 0 {
		wtype := xproto.Atom(getUint32(prop.Value))
		if wtype == wm.NetAtom[NetWMWindowTypeDock] {
			c.BW = 0
			c.OldBW = 0
			c.IsAbove = true
			c.IsFloating = true
			c.Tags = ^uint32(0)
			c.IsDock = true
			c.HintsValid = true
		}
	}

	// Clamp geometry
	if c.X+c.Width() > c.Mon.WX+c.Mon.WW {
		c.X = c.Mon.WX + c.Mon.WW - c.Width()
	}
	if c.Y+c.Height() > c.Mon.WY+c.Mon.WH {
		c.Y = c.Mon.WY + c.Mon.WH - c.Height()
	}
	c.X = max(c.X, c.Mon.WX)
	c.Y = max(c.Y, c.Mon.WY)

	if !c.IsDock {
		c.BW = int(config.BorderPx)
	}

	xproto.ConfigureWindow(wm.Conn, w,
		xproto.ConfigWindowBorderWidth, []uint32{uint32(c.BW)})
	xproto.ChangeWindowAttributes(wm.Conn, w,
		xproto.CwBorderPixel, []uint32{wm.BorderNorm})
	wm.configure(c)
	wm.updateWindowType(c)
	wm.updateSizeHints(c)
	wm.updateWMHints(c)

	xproto.ChangeWindowAttributes(wm.Conn, w, xproto.CwEventMask,
		[]uint32{xproto.EventMaskEnterWindow | xproto.EventMaskFocusChange |
			xproto.EventMaskPropertyChange | xproto.EventMaskStructureNotify})
	wm.GrabButtons(c, false)

	isTransient := transProp != nil && transProp.ValueLen > 0
	if !c.IsFloating {
		c.IsFloating = isTransient || c.IsFixed
		c.OldState = c.IsFloating
	}
	if c.IsFloating {
		wm.raiseWindow(c.Win)
	}

	wm.attachBottom(c)
	wm.attachStack(c)

	// Append to _NET_CLIENT_LIST
	xproto.ChangeProperty(wm.Conn, xproto.PropModeAppend, wm.Root,
		wm.NetAtom[NetClientList], xproto.AtomWindow, 32, 1,
		uint32ToBytes(uint32(c.Win)))

	// Move off-screen initially (trick from dwm)
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowX|xproto.ConfigWindowY|
			xproto.ConfigWindowWidth|xproto.ConfigWindowHeight,
		[]uint32{uint32(c.X + 2*wm.SW), uint32(c.Y), uint32(c.W), uint32(c.H)})

	wm.setClientState(c, icccmNormalState)

	if c.Mon == wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, false)
	}
	c.Mon.Sel = c
	wm.Arrange(c.Mon)
	xproto.MapWindow(wm.Conn, c.Win)
	wm.Focus(nil)
}

// unmanage removes a client.
func (wm *WM) unmanage(c *Client, destroyed bool) {
	m := c.Mon

	wm.detach(c)
	wm.detachStack(c)

	// Remove from minimize stack
	for i, mc := range wm.MinimizeStack {
		if mc == c {
			wm.MinimizeStack = append(wm.MinimizeStack[:i], wm.MinimizeStack[i+1:]...)
			break
		}
	}

	if !destroyed {
		xproto.ConfigureWindow(wm.Conn, c.Win,
			xproto.ConfigWindowBorderWidth, []uint32{uint32(c.OldBW)})
		xproto.ChangeWindowAttributes(wm.Conn, c.Win, xproto.CwEventMask, []uint32{xproto.EventMaskNoEvent})
		xproto.UngrabButton(wm.Conn, xproto.ButtonIndexAny, c.Win, xproto.ModMaskAny)
		wm.setClientState(c, icccmWithdrawnState)
	}

	wm.Focus(nil)
	wm.updateClientList()
	wm.Arrange(m)
}

// applyRules matches window rules against WM_CLASS.
func (wm *WM) applyRules(c *Client) {
	c.IsFloating = false
	c.Tags = 0

	classProp, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmClass, xproto.AtomString, 0, 256).Reply()

	class, instance := "broken", "broken"
	if err == nil && classProp.ValueLen > 0 {
		parts := splitWMClass(classProp.Value)
		if len(parts) >= 2 {
			instance = parts[0]
			class = parts[1]
		} else if len(parts) == 1 {
			instance = parts[0]
			class = parts[0]
		}
	}

	for _, r := range wm.ActiveRules {
		titleMatch := r.Title == "" || (c.Name != "" && contains(c.Name, r.Title))
		classMatch := r.Class == "" || contains(class, r.Class)
		instanceMatch := r.Instance == "" || contains(instance, r.Instance)

		if titleMatch && classMatch && instanceMatch {
			c.IsFloating = r.IsFloating
			c.Tags |= r.Tags
			if r.Monitor >= 0 {
				for m := wm.Mons; m != nil; m = m.Next {
					if m.Num == r.Monitor {
						c.Mon = m
						break
					}
				}
			}
		}
	}

	if c.Tags&TagMask() != 0 {
		c.Tags &= TagMask()
	} else {
		c.Tags = c.Mon.TagSet[c.Mon.SelTags]
	}
}

func contains(s, substr string) bool {
	// Simple substring match
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}


