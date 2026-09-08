package wm

import (
	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
	"github.com/jezek/xgbutil/keybind"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

func (wm *WM) handleEvent(ev xgb.Event) {
	switch e := ev.(type) {
	case randrNotifyEvent:
		wm.refreshRootGeometry()
		wm.refreshMonitorTopology()
	case xproto.ButtonPressEvent:
		wm.handleButtonPress(e)
	case xproto.ClientMessageEvent:
		wm.handleClientMessage(e)
	case xproto.ColormapNotifyEvent:
		if c := wm.clientForColormapWindow(e.Window); c != nil && c == wm.SelMon.Sel && e.New {
			wm.installClientColormaps(c)
		}
	case xproto.ConfigureRequestEvent:
		wm.handleConfigureRequest(e)
	case xproto.ConfigureNotifyEvent:
		wm.handleConfigureNotify(e)
	case xproto.DestroyNotifyEvent:
		wm.handleDestroyNotify(e)
	case xproto.MapNotifyEvent:
		wm.handleMapNotify(e)
	case xproto.EnterNotifyEvent:
		wm.handleEnterNotify(e)
	case xproto.LeaveNotifyEvent:
		wm.handleLeaveNotify(e)
	case xproto.ExposeEvent:
		wm.handleExpose(e)
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
	case xproto.SelectionClearEvent:
		if e.Selection == wm.WMSelection {
			wm.RequestQuit()
		}
	case xproto.UnmapNotifyEvent:
		wm.handleUnmapNotify(e)
	}
}

func (wm *WM) handleButtonPress(e xproto.ButtonPressEvent) {
	wm.recordUserTime(uint32(e.Time))
	click := config.ClkRootWin
	var c *Client

	util.LogDebug("buttonpress: win=0x%x button=%d state=0x%04x",
		e.Event, e.Detail, e.State)

	// Check if the click is on a titlebar window first.
	if c := wm.titlebarToClient(e.Event); c != nil {
		util.LogDebug("buttonpress: titlebar for client %q", c.Name)
		m := c.Mon
		if m != wm.SelMon {
			wm.Unfocus(wm.SelMon.Sel, true)
			wm.SelMon = m
		}
		wm.handleTitlebarButtonPress(e, c)
		return
	}

	if m := wm.winToMon(e.Event); m != nil && m != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = m
		wm.Focus(nil)
	}

	if c = wm.winToClient(e.Event); c != nil {
		util.LogDebug("buttonpress: found client %q floating=%v focused=%v",
			c.Name, c.IsFloating, c == wm.SelMon.Sel)
		wm.Focus(c)
		wm.Restack(wm.SelMon)
		click = config.ClkClientWin
	} else {
		util.LogDebug("buttonpress: no client found for win=0x%x (root=0x%x)",
			e.Event, wm.Root)
	}

	buttons := config.DefaultButtons()
	consumed := false
	for _, btn := range buttons {
		if click == btn.Click && btn.Button == xproto.Button(e.Detail) &&
			wm.cleanMask(btn.Mask) == wm.cleanMask(e.State) {
			util.LogDebug("buttonpress: matched action=%q", btn.Action)
			consumed = true
			if c != nil {
				// Floating clients use a broad synchronous passive grab so the
				// WM can raise/replay normal clicks.  For modifier actions we
				// must keep the press for the WM and release that passive grab
				// before MoveMouse/ResizeMouse installs its active grab.
				xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
				xproto.AllowEvents(wm.Conn, xproto.AllowAsyncKeyboard, xproto.TimeCurrentTime)
				wm.Conn.Sync()
			}
			if action, ok := wm.Actions[btn.Action]; ok {
				action(&btn.Arg)
			}
			return
		}
	}

	if !consumed {
		// No client action matched; replay so the click reaches the window.
		util.LogInfo("buttonpress: no binding matched, replaying pointer")
		xproto.AllowEvents(wm.Conn, xproto.AllowReplayPointer, xproto.TimeCurrentTime)
		xproto.AllowEvents(wm.Conn, xproto.AllowAsyncKeyboard, xproto.TimeCurrentTime)
	}
	// For consumed client clicks the passive grab is released before the action runs.
}

func (wm *WM) handleClientMessage(e xproto.ClientMessageEvent) {
	if e.Format != 32 {
		return
	}
	d := e.Data.Data32
	// Root-scoped requests must be handled before resolving a managed client.
	switch e.Type {
	case wm.Atoms.Get(NetCurrentDesktop):
		if d[0] < uint32(len(config.Tags)) {
			wm.View(&config.Arg{UI: 1 << d[0]})
			wm.publishCurrentDesktop()
		}
		return
	case wm.Atoms.Get(NetShowingDesktop):
		if d[0] <= 1 {
			wm.SetShowingDesktop(d[0] == 1)
		}
		return
	case wm.Atoms.Get(NetRequestFrameExtents):
		wm.setRequestedFrameExtents(e.Window)
		return
	case wm.Atoms.Get(WMProtocols):
		if xproto.Atom(d[0]) == wm.Atoms.Get(NetWMPing) {
			// PING replies target the root and identify the client in data[2].
			if c := wm.winToClient(xproto.Window(d[2])); c != nil {
				if !c.PingPending || c.PingTimestamp != d[1] {
					return
				}
				c.PingPending = false
				c.Unresponsive = false
				c.DemandsAttention = false
				wm.publishClientState(c)
			}
		}
		return
	}

	c := wm.winToClient(e.Window)
	if c == nil {
		return
	}

	switch e.Type {
	case wm.Atoms.Get(NetWMState):
		wm.applyNetWMStateMessage(c, d)
	case wm.Atoms.Get(NetActiveWindow):
		wm.handleActivationRequest(c, d[0], d[1])
	case wm.Atoms.Get(NetWMDesktop):
		wm.moveClientToDesktop(c, d[0])
	case wm.Atoms.Get(NetCloseWindow):
		wm.closeClient(c, d[0])
	case wm.Atoms.Get(NetMoveResizeWindow):
		wm.handleNetMoveResizeWindow(c, d)
	case wm.Atoms.Get(NetWMMoveResize):
		wm.handleNetWMMoveResize(c, d)
	case wm.Atoms.Get(NetRestackWindow):
		wm.handleNetRestack(c, xproto.Window(d[1]), d[2])
	case wm.Atoms.Get(NetWMFullscreenMonitors):
		wm.setFullscreenMonitors(c, d)
	case wm.Atoms.Get(WMChangeState):
		if d[0] == icccmIconicState {
			wm.minimizeClient(c)
		}
	}
}

func (wm *WM) handleConfigureRequest(e xproto.ConfigureRequestEvent) {
	c := wm.winToClient(e.Window)
	if c != nil {
		if c.IsDock {
			return
		}
		valueMask := e.ValueMask &^ xproto.ConfigWindowBorderWidth
		if c.IsFloating || wm.SelMon.Lt.Arrange == nil {
			m := c.Mon
			x, y, w, h := c.X, c.Y, c.W, c.H
			if valueMask&xproto.ConfigWindowX != 0 {
				x = m.MX + int(e.X)
			}
			if valueMask&xproto.ConfigWindowY != 0 {
				y = m.MY + int(e.Y)
			}
			if valueMask&xproto.ConfigWindowWidth != 0 {
				w = int(e.Width)
			}
			if valueMask&xproto.ConfigWindowHeight != 0 {
				h = int(e.Height)
			}
			if (x+w) > m.MX+m.MW && c.IsFloating {
				x = m.MX + (m.MW/2 - w/2)
			}
			if (y+h) > m.MY+m.MH && c.IsFloating {
				y = m.MY + (m.MH/2 - h/2)
			}
			if wm.clientVisible(c) {
				wm.resizeClient(c, x, y, w, h)
			} else {
				c.OldX, c.OldY, c.OldW, c.OldH = c.X, c.Y, c.W, c.H
				c.X, c.Y, c.W, c.H = x, y, w, h
				wm.configure(c)
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
			wm.stackingDirty = true
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
		wm.setRootCardinals(NetDesktopGeometry, uint32(max(wm.SW, 1)), uint32(max(wm.SH, 1)))
		wm.publishWorkareaFromStruts()
		wm.publishSupported()
		for m := wm.Mons; m != nil; m = m.Next {
			for c := m.Clients; c != nil; c = c.Next {
				if c.IsFullscreen {
					wm.applyFullscreenGeometry(c)
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
	} else if _, ok := wm.DockStruts[e.Window]; ok {
		delete(wm.DockStruts, e.Window)
		wm.publishWorkareaFromStruts()
	}
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.UserTimeWindow == e.Window {
				c.UserTimeWindow = xproto.WindowNone
			}
		}
	}
}

func (wm *WM) handleMapNotify(e xproto.MapNotifyEvent) {
	if wm.winToClient(e.Window) == nil {
		wm.updateExternalDockStrut(e.Window)
	}
}

func (wm *WM) handleEnterNotify(e xproto.EnterNotifyEvent) {
	if (e.Mode != xproto.NotifyModeNormal || e.Detail == xproto.NotifyDetailInferior) && e.Event != wm.Root {
		return
	}
	// Ignore enter events on titlebar windows – they belong to the client.
	if wm.titlebarToClient(e.Event) != nil {
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

func (wm *WM) handleExpose(e xproto.ExposeEvent) {
	// Only redraw on the last expose in a series (Count == 0).
	if e.Count != 0 {
		return
	}
	if c := wm.titlebarToClient(e.Window); c != nil {
		wm.drawTitlebar(c)
	}
}

func (wm *WM) handleKeyPress(e xproto.KeyPressEvent) {
	wm.recordUserTime(uint32(e.Time))
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
	if e.Request == xproto.MappingKeyboard || e.Request == xproto.MappingModifier {
		wm.GrabKeys()
		for _, c := range wm.ManageOrder {
			wm.GrabButtons(c, c == wm.Focused)
		}
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
	// Update titlebar button hover state.
	if c := wm.titlebarToClient(e.Event); c != nil {
		hit := hitTestTitlebar(int(e.EventX), int(e.EventY))
		newHover := hit
		if newHover == tbDragArea {
			newHover = tbNone
		}
		if newHover != c.TitleHover {
			c.TitleHover = newHover
			wm.drawTitlebar(c)
		}
		return
	}
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

func (wm *WM) handleLeaveNotify(e xproto.LeaveNotifyEvent) {
	if c := wm.titlebarToClient(e.Event); c != nil {
		if c.TitleHover != tbNone {
			c.TitleHover = tbNone
			wm.drawTitlebar(c)
		}
	}
}

func (wm *WM) handlePropertyNotify(e xproto.PropertyNotifyEvent) {
	if e.Window == wm.Root {
		if e.State == xproto.PropertyDelete {
			if e.Atom == wm.Atoms.Get(NetClientList) {
				wm.updateClientList()
			}
			if e.Atom == wm.Atoms.Get(NetClientListStacking) {
				wm.stackingPublished = false
				wm.stackingDirty = true
			}
		}
		if e.Atom == wm.Atoms.Get(NetDesktopNames) && e.State != xproto.PropertyDelete {
			wm.acceptDesktopNames()
		}
		return
	}

	c := wm.winToClient(e.Window)
	if c == nil {
		if e.Atom == wm.Atoms.Get(NetWMUserTime) {
			for m := wm.Mons; m != nil; m = m.Next {
				for candidate := m.Clients; candidate != nil; candidate = candidate.Next {
					if candidate.UserTimeWindow == e.Window {
						wm.updateUserTime(candidate)
					}
				}
			}
		}
		if e.Atom == wm.Atoms.Get(NetWMStrut) || e.Atom == wm.Atoms.Get(NetWMStrutPartial) ||
			e.Atom == wm.Atoms.Get(NetWMWindowType) {
			wm.updateExternalDockStrut(e.Window)
		}
		return
	}
	switch e.Atom {
	case xproto.AtomWmTransientFor:
		prop, err := xproto.GetProperty(wm.Conn, false, c.Win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		c.TransientFor = xproto.WindowNone
		if err == nil && prop.ValueLen > 0 {
			c.TransientFor = xproto.Window(getUint32(prop.Value))
			if wm.winToClient(c.TransientFor) != nil && !c.IsFloating {
				c.IsFloating = true
				wm.Arrange(c.Mon)
			}
		}
	case xproto.AtomWmClass:
		wm.updateWMClass(c)
	case xproto.AtomWmNormalHints:
		c.HintsValid = false
		wm.updateSizeHints(c)
		wm.publishAllowedActions(c)
	case xproto.AtomWmHints:
		wm.updateWMHints(c)
	case wm.Atoms.Get(WMColormapWindows):
		wm.updateColormapWindows(c)
	}

	if e.Atom == xproto.AtomWmName || e.Atom == wm.Atoms.Get(NetWMName) {
		wm.updateTitle(c)
		wm.drawTitlebar(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMWindowType) {
		wm.updateWindowType(c)
		wm.publishClientDesktop(c)
		wm.publishClientState(c)
		wm.Arrange(c.Mon)
		wm.Restack(c.Mon)
	}
	if e.Atom == wm.Atoms.Get(NetWMState) && e.State == xproto.PropertyDelete {
		c.statePublished = false
		wm.publishClientState(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMDesktop) && e.State == xproto.PropertyDelete {
		wm.publishClientDesktop(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMAllowedActions) && e.State == xproto.PropertyDelete {
		wm.publishAllowedActions(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMStrut) || e.Atom == wm.Atoms.Get(NetWMStrutPartial) {
		wm.updateStrut(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMWindowOpacity) {
		wm.forwardWindowOpacity(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMUserTime) || e.Atom == wm.Atoms.Get(NetWMUserTimeWindow) {
		wm.updateUserTime(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMFullscreenMonitors) {
		wm.updateFullscreenMonitors(c)
	}
	if e.Atom == wm.Atoms.Get(NetWMSyncRequestCounter) {
		wm.updateSyncCounter(c)
	}
}

func (wm *WM) handleUnmapNotify(e xproto.UnmapNotifyEvent) {
	c := wm.winToClient(e.Window)
	if c == nil {
		if _, ok := wm.DockStruts[e.Window]; ok {
			delete(wm.DockStruts, e.Window)
			wm.publishWorkareaFromStruts()
		}
		return
	}
	if c.IgnoreUnmap > 0 {
		c.IgnoreUnmap--
		return
	}
	wm.unmanage(c, false)
}

// manage creates a Client for a newly-mapped window.
func (wm *WM) manage(w xproto.Window, wa *xproto.GetWindowAttributesReply) {
	wtypes := wm.getWindowAtomProps(w, wm.Atoms.Get(NetWMWindowType), 32)
	wasIconic := wm.getState(w) == icccmIconicState

	// Get geometry
	geom, err := xproto.GetGeometry(wm.Conn, xproto.Drawable(w)).Reply()
	if err != nil {
		return
	}

	c := &Client{
		Win:   w,
		X:     int(geom.X),
		Y:     int(geom.Y),
		W:     int(geom.Width),
		H:     int(geom.Height),
		OldX:  int(geom.X),
		OldY:  int(geom.Y),
		OldW:  int(geom.Width),
		OldH:  int(geom.Height),
		OldBW: int(geom.BorderWidth),
	}

	wm.updateWMClass(c)
	wm.updateTitle(c)

	// Check transient
	transProp, err := xproto.GetProperty(wm.Conn, false, w,
		xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
	if err == nil && transProp.ValueLen > 0 {
		transWin := xproto.Window(getUint32(transProp.Value))
		c.TransientFor = transWin
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
	wtypes = wm.getWindowAtomProps(w, wm.Atoms.Get(NetWMWindowType), 32)
	if len(wtypes) > 0 {
		if atomListContains(wtypes, wm.Atoms.Get(NetWMWindowTypeDock)) {
			c.BW = 0
			c.OldBW = 0
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
		xproto.ConfigWindowBorderWidth, []uint32{0})
	xproto.ChangeWindowAttributes(wm.Conn, w,
		xproto.CwBorderPixel, []uint32{wm.BorderNorm})
	wm.setFrameExtents(c, 0)
	wm.configure(c)
	wm.updateWindowType(c)
	wm.updateSizeHints(c)
	wm.updateWMHints(c)
	wm.updateColormapWindows(c)
	initialIconic := c.InitialIconic || wasIconic
	c.Minimized = false
	wm.ClientMap[c.Win] = c
	wm.ManageOrder = append(wm.ManageOrder, c)
	wm.updateClientList()
	wm.NextManageSeq++
	c.ManageSeq = wm.NextManageSeq
	wm.applyInitialDesktop(c)
	wm.publishClientDesktop(c)
	wm.publishAllowedActions(c)
	wm.updateStrut(c)
	wm.updateUserTime(c)
	wm.updateFullscreenMonitors(c)
	wm.updateSyncCounter(c)

	xproto.ChangeWindowAttributes(wm.Conn, w, xproto.CwEventMask,
		[]uint32{xproto.EventMaskEnterWindow | xproto.EventMaskFocusChange |
			xproto.EventMaskPropertyChange | xproto.EventMaskStructureNotify})
	wm.GrabButtons(c, false)

	isTransient := transProp != nil && transProp.ValueLen > 0
	if !c.IsFloating {
		c.IsFloating = isTransient || c.IsFixed
		c.OldState = c.IsFloating
	}
	wm.placeFloatingOnManage(c)
	wm.attachBottom(c)
	wm.attachStack(c)
	xproto.ChangeSaveSet(wm.Conn, xproto.SetModeInsert, c.Win)
	wm.applyInitialState(c)

	// Move off-screen initially (trick from dwm)
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowX|xproto.ConfigWindowY|
			xproto.ConfigWindowWidth|xproto.ConfigWindowHeight,
		[]uint32{uint32(c.X + 2*wm.SW), uint32(c.Y), uint32(c.W), uint32(c.H)})

	if initialIconic {
		c.Minimized = true
		wm.MinimizeStack = append(wm.MinimizeStack, c)
		wm.setClientState(c, icccmIconicState)
	} else {
		wm.setClientState(c, icccmNormalState)
	}

	if c.Mon == wm.SelMon && !c.NeverFocus && !initialIconic {
		wm.Unfocus(wm.SelMon.Sel, false)
	}
	if !c.NeverFocus && !initialIconic {
		c.Mon.Sel = c
	}
	wm.Arrange(c.Mon)
	wm.forwardWindowOpacity(c)
	if initialIconic {
		wm.publishClientState(c)
		wm.Focus(nil)
	} else if c.NeverFocus {
		xproto.MapWindow(wm.Conn, c.Win)
		c.HasMapped = true
		wm.showBorderWindow(c)
		if c.IsFloating && !c.IsDock && !c.IsFullscreen {
			wm.createTitlebar(c)
		}
		wm.Focus(nil)
	} else {
		xproto.MapWindow(wm.Conn, c.Win)
		c.HasMapped = true
		wm.showBorderWindow(c)
		if c.IsFloating && !c.IsDock && !c.IsFullscreen {
			wm.createTitlebar(c)
		}
		wm.Focus(c)
	}
	wm.Restack(c.Mon)
	wm.updateClientListStacking()
}

// unmanage removes a client.
func (wm *WM) unmanage(c *Client, destroyed bool) {
	m := c.Mon
	delete(wm.ClientMap, c.Win)
	for i, candidate := range wm.ManageOrder {
		if candidate == c {
			wm.ManageOrder = append(wm.ManageOrder[:i], wm.ManageOrder[i+1:]...)
			break
		}
	}
	wm.updateClientList()
	if wm.Focused == c {
		wm.Focused = nil
	}
	if wm.ShowDesktopFocus == c {
		wm.ShowDesktopFocus = nil
	}
	for i := len(wm.MinimizeStack) - 1; i >= 0; i-- {
		if wm.MinimizeStack[i] == c {
			wm.MinimizeStack = append(wm.MinimizeStack[:i], wm.MinimizeStack[i+1:]...)
		}
	}

	wm.destroyTitlebar(c)
	wm.destroyBorderWindow(c)
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
		xproto.ChangeSaveSet(wm.Conn, xproto.SetModeDelete, c.Win)
		if !wm.ShuttingDown {
			wm.setClientState(c, icccmWithdrawnState)
			for _, property := range []AtomName{NetWMDesktop, NetWMState, NetWMAllowedActions,
				NetFrameExtents, NetWMFullscreenMonitors} {
				xproto.DeleteProperty(wm.Conn, c.Win, wm.Atoms.Get(property))
			}
		}
	}
	delete(wm.DockStruts, c.Win)
	wm.publishWorkareaFromStruts()

	wm.Focus(nil)
	wm.updateClientListStacking()
	wm.Arrange(m)
}

// applyRules matches window rules against WM_CLASS.
func (wm *WM) applyRules(c *Client) {
	c.IsFloating = false
	c.Tags = 0

	class, instance := c.Class, c.Instance

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
