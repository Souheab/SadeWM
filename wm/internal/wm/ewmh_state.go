package wm

import (
	"strings"
	"time"

	"github.com/jezek/xgb/xproto"
	"github.com/jezek/xgbutil/keybind"
	"github.com/sadewm/sadewm/wm/internal/config"
)

const (
	netWMStateRemove = 0
	netWMStateAdd    = 1
	netWMStateToggle = 2
)

func requestedState(action uint32, current bool) (bool, bool) {
	switch action {
	case netWMStateRemove:
		return false, true
	case netWMStateAdd:
		return true, true
	case netWMStateToggle:
		return !current, true
	default:
		return current, false
	}
}

func (wm *WM) applyInitialState(c *Client) {
	for _, atom := range wm.getAtomProps(c, wm.Atoms.Get(NetWMState), 64) {
		wm.applyStateAtom(c, atom, netWMStateAdd, true)
	}
	wm.publishClientState(c)
}

func (wm *WM) applyNetWMStateMessage(c *Client, data []uint32) {
	if len(data) < 3 {
		return
	}
	if data[0] > netWMStateToggle {
		return
	}
	for _, raw := range data[1:3] {
		if raw != 0 {
			wm.applyStateAtom(c, xproto.Atom(raw), data[0], false)
		}
	}
	wm.publishClientState(c)
	wm.publishAllowedActions(c)
	wm.Arrange(c.Mon)
	wm.Restack(c.Mon)
}

func (wm *WM) applyStateAtom(c *Client, atom xproto.Atom, action uint32, initial bool) {
	set := func(current bool) (bool, bool) { return requestedState(action, current) }
	switch atom {
	case wm.Atoms.Get(NetWMStateModal):
		if value, ok := set(c.IsModal); ok {
			c.IsModal = value
			if value {
				c.IsFloating = true
			}
		}
	case wm.Atoms.Get(NetWMStateSticky):
		if value, ok := set(c.IsSticky); ok {
			c.IsSticky = value
		}
	case wm.Atoms.Get(NetWMStateMaximizedVert):
		if value, ok := set(c.MaximizedVert); ok {
			wm.setMaximizedAxes(c, c.MaximizedHorz, value)
		}
	case wm.Atoms.Get(NetWMStateMaximizedHorz):
		if value, ok := set(c.MaximizedHorz); ok {
			wm.setMaximizedAxes(c, value, c.MaximizedVert)
		}
	case wm.Atoms.Get(NetWMStateShaded):
		if value, ok := set(c.IsShaded); ok {
			wm.setShaded(c, value)
		}
	case wm.Atoms.Get(NetWMStateSkipTaskbar):
		if value, ok := set(c.SkipTaskbar); ok {
			c.SkipTaskbar = value
		}
	case wm.Atoms.Get(NetWMStateSkipPager):
		if value, ok := set(c.SkipPager); ok {
			c.SkipPager = value
		}
	case wm.Atoms.Get(NetWMFullscreen):
		if value, ok := set(c.IsFullscreen); ok {
			wm.SetFullscreen(c, value)
		}
	case wm.Atoms.Get(NetWMStateAbove), wm.Atoms.Get(NetWMStateStaysOnTop):
		if value, ok := set(c.IsAbove); ok {
			if value {
				c.IsBelow = false
			}
			wm.SetAbove(c, value)
		}
	case wm.Atoms.Get(NetWMStateBelow):
		if value, ok := set(c.IsBelow); ok {
			c.IsBelow = value
			if value {
				c.IsAbove = false
			}
		}
	case wm.Atoms.Get(NetWMStateDemandsAttention):
		if value, ok := set(c.DemandsAttention); ok {
			c.DemandsAttention = value
			wm.setUrgent(c, value)
		}
	case wm.Atoms.Get(NetWMStateHidden), wm.Atoms.Get(NetWMStateFocused):
		// Read-only states are derived by the WM.
	default:
		_ = initial // Unknown _NET states are deliberately canonicalized away.
	}
}

func (c *Client) rememberNormalGeometry() {
	if c.NormalGeometryValid {
		return
	}
	c.NormalX, c.NormalY, c.NormalW, c.NormalH = c.X, c.Y, c.W, c.H
	c.StateRestoreFloating = c.IsFloating
	c.NormalGeometryValid = true
}

func (wm *WM) setMaximizedAxes(c *Client, horizontal, vertical bool) {
	if horizontal || vertical {
		c.rememberNormalGeometry()
		if !c.IsFloating {
			c.IsFloating = true
			wm.createTitlebar(c)
		}
	}
	c.MaximizedHorz, c.MaximizedVert = horizontal, vertical
	c.Maximized = horizontal && vertical
	if c.IsFullscreen || c.IsShaded {
		return
	}
	if !horizontal && !vertical {
		if c.NormalGeometryValid {
			wm.Resize(c, c.NormalX, c.NormalY, c.NormalW, c.NormalH, false)
			c.IsFloating = c.StateRestoreFloating
			c.NormalGeometryValid = false
			if !c.IsFloating {
				wm.destroyTitlebar(c)
			}
		}
		return
	}
	x, y, width, height := c.X, c.Y, c.W, c.H
	if c.NormalGeometryValid {
		x, y, width, height = c.NormalX, c.NormalY, c.NormalW, c.NormalH
	}
	if horizontal {
		x, width = c.Mon.WX, c.Mon.WW-2*c.BW
	}
	if vertical {
		y, height = c.Mon.WY, c.Mon.WH-2*c.BW
	}
	wm.Resize(c, x, y, width, height, false)
}

func (wm *WM) setShaded(c *Client, shaded bool) {
	if shaded == c.IsShaded {
		return
	}
	if c.IsFullscreen {
		c.IsShaded = shaded
		return
	}
	if shaded {
		c.rememberNormalGeometry()
		c.IsFloating = true
		wm.createTitlebar(c)
		c.IgnoreUnmap += 2
		xproto.UnmapWindow(wm.Conn, c.Win)
		if c.FrameWin != 0 {
			xproto.ConfigureWindow(wm.Conn, c.FrameWin, xproto.ConfigWindowHeight,
				[]uint32{titlebarHeight})
		}
		c.IsShaded = true
	} else {
		c.IsShaded = false
		xproto.MapWindow(wm.Conn, c.Win)
		if c.MaximizedHorz || c.MaximizedVert {
			wm.setMaximizedAxes(c, c.MaximizedHorz, c.MaximizedVert)
		} else if c.NormalGeometryValid {
			wm.Resize(c, c.NormalX, c.NormalY, c.NormalW, c.NormalH, false)
			c.IsFloating = c.StateRestoreFloating
			c.NormalGeometryValid = false
			if !c.IsFloating {
				wm.destroyTitlebar(c)
			}
		}
	}
}

func (wm *WM) applyInitialDesktop(c *Client) {
	if c.IsDock || c.IsDesktop {
		c.Tags = TagMask()
		return
	}
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win, wm.Atoms.Get(NetWMDesktop),
		xproto.AtomCardinal, 0, 1).Reply()
	if err != nil || reply.ValueLen == 0 {
		return
	}
	wm.moveClientToDesktop(c, getUint32(reply.Value))
}

func (wm *WM) moveClientToDesktop(c *Client, desktop uint32) {
	if c.IsDock || c.IsDesktop {
		c.Tags = TagMask()
		wm.publishClientDesktop(c)
		return
	}
	if desktop == ^uint32(0) {
		c.Tags = TagMask()
	} else if desktop < uint32(len(config.Tags)) {
		c.Tags = 1 << desktop
	} else {
		return
	}
	wm.publishClientDesktop(c)
	wm.Focus(nil)
	wm.Arrange(c.Mon)
}

func xTimeNotBefore(value, reference uint32) bool {
	return int32(value-reference) >= 0
}

func (wm *WM) handleActivationRequest(c *Client, source, timestamp uint32) {
	allowed := source == 2 || c == wm.SelMon.Sel ||
		(timestamp != 0 && xTimeNotBefore(timestamp, wm.LastUserTime))
	if !allowed {
		c.DemandsAttention = true
		wm.setUrgent(c, true)
		wm.publishClientState(c)
		return
	}
	if c.Minimized {
		wm.restoreClient(c)
	}
	if wm.ShowingDesktop {
		wm.SetShowingDesktop(false)
	}
	if !c.IsVisible() {
		wm.SelMon = c.Mon
		wm.View(&config.Arg{UI: 1 << desktopForTags(c.Tags)})
	}
	c.DemandsAttention = false
	wm.setUrgent(c, false)
	wm.Focus(c)
	wm.Restack(c.Mon)
}

func (wm *WM) setRequestedFrameExtents(win xproto.Window) {
	top := uint32(0)
	wtypes := wm.getWindowAtomProps(win, wm.Atoms.Get(NetWMWindowType), 32)
	if wm.hasFloatingWindowType(wtypes) {
		top = titlebarHeight
	}
	data := []uint32{0, 0, top, 0}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, win,
		wm.Atoms.Get(NetFrameExtents), xproto.AtomCardinal, 32, 4, uint32sToBytes(data))
}

func (wm *WM) handleNetMoveResizeWindow(c *Client, data []uint32) {
	if len(data) < 5 {
		return
	}
	flags := data[0]
	if c.IsFullscreen {
		wm.SetFullscreen(c, false)
	}
	if c.MaximizedHorz || c.MaximizedVert {
		wm.setMaximizedAxes(c, false, false)
	}
	if c.IsShaded {
		wm.setShaded(c, false)
	}
	if !c.IsFloating {
		c.IsFloating = true
		wm.createTitlebar(c)
	}
	x, y, width, height := c.X, c.Y, c.W, c.H
	gravity := byte(flags & 0xff)
	if gravity == 0 {
		gravity = c.WinGravity
	}
	gravityX, gravityY := gravityDecorationOffset(gravity, 0, 0, frameTopExtent(c), 0)
	if flags&(1<<8) != 0 {
		x = int(int32(data[1])) + gravityX
	}
	if flags&(1<<9) != 0 {
		y = int(int32(data[2])) + gravityY
	}
	if flags&(1<<10) != 0 {
		width = int(data[3])
	}
	if flags&(1<<11) != 0 {
		height = int(data[4])
	}
	wm.Resize(c, x, y, width, height, true)
	wm.publishClientState(c)
}

func frameTopExtent(c *Client) int {
	if c != nil && c.FrameWin != xproto.WindowNone {
		return titlebarHeight
	}
	return 0
}

func gravityDecorationOffset(gravity byte, left, right, top, bottom int) (int, int) {
	switch gravity {
	case xproto.GravityNorthWest, xproto.GravityNorth, xproto.GravityNorthEast:
		return left, top
	case xproto.GravityWest, xproto.GravityCenter, xproto.GravityEast:
		return (left - right) / 2, (top - bottom) / 2
	case xproto.GravitySouthWest, xproto.GravitySouth, xproto.GravitySouthEast,
		xproto.GravityStatic:
		return -right, -bottom
	default:
		return left, top
	}
}

func (wm *WM) handleNetWMMoveResize(c *Client, data []uint32) {
	if len(data) < 4 {
		return
	}
	direction := data[2]
	if direction == 11 {
		xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
		xproto.UngrabKeyboard(wm.Conn, xproto.TimeCurrentTime)
		return
	}
	if direction > 10 {
		return
	}
	wm.beginExternalMoveResize(c, int(int32(data[0])), int(int32(data[1])), direction, byte(data[3]))
}

func (wm *WM) beginExternalMoveResize(c *Client, startX, startY int, direction uint32, button byte) {
	if c == nil || c.IsDock || c.IsDesktop {
		return
	}
	if c.IsFullscreen {
		wm.SetFullscreen(c, false)
	}
	if c.MaximizedHorz || c.MaximizedVert {
		wm.setMaximizedAxes(c, false, false)
	}
	if c.IsShaded {
		wm.setShaded(c, false)
	}
	if !c.IsFloating {
		c.IsFloating = true
		wm.createTitlebar(c)
	}
	wm.Focus(c)
	wm.Restack(c.Mon)
	if startX == 0 && startY == 0 {
		startX, startY = wm.getRootPtr()
	}
	origX, origY, origW, origH := c.X, c.Y, c.W, c.H
	keyboard := direction == 9 || direction == 10
	if keyboard {
		reply, err := xproto.GrabKeyboard(wm.Conn, false, wm.Root, xproto.TimeCurrentTime,
			xproto.GrabModeAsync, xproto.GrabModeAsync).Reply()
		if err != nil || reply == nil || reply.Status != xproto.GrabStatusSuccess {
			return
		}
		defer xproto.UngrabKeyboard(wm.Conn, xproto.TimeCurrentTime)
	} else {
		reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
			xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
			xproto.GrabModeAsync, xproto.GrabModeAsync, xproto.WindowNone,
			wm.Cursors[CurResize], xproto.TimeCurrentTime).Reply()
		if err != nil || reply == nil || reply.Status != xproto.GrabStatusSuccess {
			return
		}
		defer xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
	}
	wm.dragging = true
	defer func() {
		wm.dragging = false
		wm.replayPendingEvts()
	}()
	cancelled := false
	for {
		ev := wm.nextDragEvent()
		if ev == nil {
			break
		}
		switch e := ev.(type) {
		case xproto.MotionNotifyEvent:
			if keyboard {
				continue
			}
			dx, dy := int(e.RootX)-startX, int(e.RootY)-startY
			x, y, width, height := moveResizeGeometry(origX, origY, origW, origH, dx, dy, direction)
			wm.Resize(c, x, y, width, height, true)
		case xproto.KeyPressEvent:
			if !keyboard {
				wm.pendingEvts = append(wm.pendingEvts, ev)
				continue
			}
			key := keybind.LookupString(wm.X, e.State, e.Detail)
			if key == "Escape" {
				cancelled = true
				goto done
			}
			if key == "Return" || key == "KP_Enter" {
				goto done
			}
			dx, dy := 0, 0
			switch key {
			case "Left":
				dx = -10
			case "Right":
				dx = 10
			case "Up":
				dy = -10
			case "Down":
				dy = 10
			default:
				continue
			}
			if direction == 10 {
				wm.Resize(c, c.X+dx, c.Y+dy, c.W, c.H, true)
			} else {
				wm.Resize(c, c.X, c.Y, max(1, c.W+dx), max(1, c.H+dy), true)
			}
		case xproto.ButtonReleaseEvent:
			if !keyboard && (button == 0 || byte(e.Detail) == button) {
				goto done
			}
		case xproto.ClientMessageEvent:
			if e.Type == wm.Atoms.Get(NetWMMoveResize) && e.Data.Data32[2] == 11 {
				cancelled = true
				goto done
			}
			wm.pendingEvts = append(wm.pendingEvts, ev)
		case xproto.ConfigureRequestEvent:
			wm.handleConfigureRequest(e)
		case xproto.MapRequestEvent:
			wm.handleMapRequest(e)
		default:
			wm.pendingEvts = append(wm.pendingEvts, ev)
		}
	}
done:
	if cancelled {
		wm.Resize(c, origX, origY, origW, origH, true)
	}
	wm.publishClientState(c)
}

func moveResizeGeometry(x, y, width, height, dx, dy int, direction uint32) (int, int, int, int) {
	switch direction {
	case 0: // top-left
		x, y, width, height = x+dx, y+dy, width-dx, height-dy
	case 1: // top
		y, height = y+dy, height-dy
	case 2: // top-right
		y, width, height = y+dy, width+dx, height-dy
	case 3: // right
		width += dx
	case 4: // bottom-right
		width, height = width+dx, height+dy
	case 5: // bottom
		height += dy
	case 6: // bottom-left
		x, width, height = x+dx, width-dx, height+dy
	case 7: // left
		x, width = x+dx, width-dx
	case 8: // move
		x, y = x+dx, y+dy
	}
	if width < 1 {
		x += width - 1
		width = 1
	}
	if height < 1 {
		y += height - 1
		height = 1
	}
	return x, y, width, height
}

func (wm *WM) handleNetRestack(c *Client, sibling xproto.Window, detail uint32) {
	if detail > uint32(xproto.StackModeOpposite) {
		return
	}
	values := []uint32{}
	mask := uint16(0)
	if sibling != xproto.WindowNone {
		if siblingClient := wm.winToClient(sibling); siblingClient != nil {
			sibling = wm.stackWindow(siblingClient)
		}
		values = append(values, uint32(sibling))
		mask |= xproto.ConfigWindowSibling
	}
	values = append(values, detail)
	mask |= xproto.ConfigWindowStackMode
	xproto.ConfigureWindow(wm.Conn, wm.stackWindow(c), mask, values)
	wm.updateClientListStacking()
}

func (wm *WM) setFullscreenMonitors(c *Client, data []uint32) {
	if len(data) < 4 {
		return
	}
	monitors := wm.monitorSlice()
	for i := 0; i < 4; i++ {
		if int(data[i]) >= len(monitors) {
			return
		}
	}
	if _, _, _, _, ok := fullscreenBounds(monitors, [4]uint32{data[0], data[1], data[2], data[3]}); !ok {
		return
	}
	for i := 0; i < 4; i++ {
		c.FullscreenMonitors[i] = data[i]
	}
	c.HasFullscreenMonitors = true
	wm.setWindowCardinals(c.Win, NetWMFullscreenMonitors, data[0], data[1], data[2], data[3])
	if c.IsFullscreen {
		wm.applyFullscreenGeometry(c)
	}
}

func (wm *WM) updateStrut(c *Client) {
	values := wm.getWindowCardinals(c.Win, NetWMStrutPartial, 12)
	if len(values) < 12 {
		basic := wm.getWindowCardinals(c.Win, NetWMStrut, 4)
		if len(basic) == 4 {
			values = make([]uint32, 12)
			copy(values, basic)
			values[5], values[7] = uint32(max(wm.SH-1, 0)), uint32(max(wm.SH-1, 0))
			values[9], values[11] = uint32(max(wm.SW-1, 0)), uint32(max(wm.SW-1, 0))
		}
	}
	c.HasStrut = len(values) == 12
	if c.HasStrut {
		copy(c.Strut[:], values)
		wm.DockStruts[c.Win] = c.Strut
	} else {
		delete(wm.DockStruts, c.Win)
	}
	wm.recomputeWorkAreas()
	wm.publishWorkareaFromStruts()
}

func (wm *WM) updateExternalDockStrut(win xproto.Window) {
	if win == xproto.WindowNone || win == wm.Root || win == wm.WMCheckWin {
		return
	}
	attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
	if err != nil || attrs.MapState == xproto.MapStateUnmapped {
		delete(wm.DockStruts, win)
		wm.publishWorkareaFromStruts()
		return
	}
	types := wm.getWindowAtomProps(win, wm.Atoms.Get(NetWMWindowType), 32)
	if !attrs.OverrideRedirect || !atomListContains(types, wm.Atoms.Get(NetWMWindowTypeDock)) {
		return
	}
	values := wm.getWindowCardinals(win, NetWMStrutPartial, 12)
	if len(values) < 12 {
		basic := wm.getWindowCardinals(win, NetWMStrut, 4)
		if len(basic) == 4 {
			values = make([]uint32, 12)
			copy(values, basic)
			values[5], values[7] = uint32(max(wm.SH-1, 0)), uint32(max(wm.SH-1, 0))
			values[9], values[11] = uint32(max(wm.SW-1, 0)), uint32(max(wm.SW-1, 0))
		}
	}
	if len(values) == 12 {
		var strut [12]uint32
		copy(strut[:], values)
		wm.DockStruts[win] = strut
		wm.selectAdditionalEvents(win, xproto.EventMaskPropertyChange|xproto.EventMaskStructureNotify)
	} else {
		delete(wm.DockStruts, win)
	}
	wm.publishWorkareaFromStruts()
}

func (wm *WM) getWindowCardinals(win xproto.Window, name AtomName, count uint32) []uint32 {
	reply, err := xproto.GetProperty(wm.Conn, false, win, wm.Atoms.Get(name),
		xproto.AtomCardinal, 0, count).Reply()
	if err != nil || reply.ValueLen == 0 {
		return nil
	}
	values := make([]uint32, reply.ValueLen)
	for i := range values {
		values[i] = getUint32(reply.Value[i*4:])
	}
	return values
}

func (wm *WM) publishWorkareaFromStruts() {
	left, right := uint32(0), uint32(0)
	top, bottom := uint32(wm.TopOffset), uint32(wm.BottomOffset)
	for _, s := range wm.DockStruts {
		left = max(left, min(s[0], uint32(max(wm.SW-1, 0))))
		right = max(right, min(s[1], uint32(max(wm.SW-1, 0))))
		top = max(top, min(s[2], uint32(max(wm.SH-1, 0))))
		bottom = max(bottom, min(s[3], uint32(max(wm.SH-1, 0))))
	}
	if int(left)+int(right) >= wm.SW {
		right = uint32(max(wm.SW-int(left)-1, 0))
	}
	if int(top)+int(bottom) >= wm.SH {
		bottom = uint32(max(wm.SH-int(top)-1, 0))
	}
	width := max(wm.SW-int(left)-int(right), 1)
	height := max(wm.SH-int(top)-int(bottom), 1)
	values := make([]uint32, 0, max(len(config.Tags), 1)*4)
	for range max(len(config.Tags), 1) {
		values = append(values, left, top, uint32(width), uint32(height))
	}
	wm.setRootCardinals(NetWorkarea, values...)
	for m := wm.Mons; m != nil; m = m.Next {
		wm.applyMonitorStruts(m)
	}
	if wm.Conn != nil {
		wm.Arrange(nil)
	}
}

func spansIntersect(a0, a1 int, b0, b1 uint32) bool {
	return a0 <= int(b1) && a1-1 >= int(b0)
}

func (wm *WM) applyMonitorStruts(m *Monitor) {
	left, right := m.MX, m.MX+m.MW
	top := m.MY + min(int(wm.TopOffset), m.MH)
	bottom := m.MY + m.MH - min(int(wm.BottomOffset), m.MH)
	for _, s := range wm.DockStruts {
		if s[0] > 0 && spansIntersect(m.MY, m.MY+m.MH, s[4], s[5]) {
			left = max(left, int(s[0]))
		}
		if s[1] > 0 && spansIntersect(m.MY, m.MY+m.MH, s[6], s[7]) {
			right = min(right, wm.SW-int(s[1]))
		}
		if s[2] > 0 && spansIntersect(m.MX, m.MX+m.MW, s[8], s[9]) {
			top = max(top, int(s[2]))
		}
		if s[3] > 0 && spansIntersect(m.MX, m.MX+m.MW, s[10], s[11]) {
			bottom = min(bottom, wm.SH-int(s[3]))
		}
	}
	m.WX, m.WY = min(left, m.MX+m.MW-1), min(top, m.MY+m.MH-1)
	m.WW, m.WH = max(1, right-m.WX), max(1, bottom-m.WY)
}

func (wm *WM) forwardWindowOpacity(c *Client) {
	if c.FrameWin == 0 {
		return
	}
	values := wm.getWindowCardinals(c.Win, NetWMWindowOpacity, 1)
	if len(values) == 1 {
		wm.setWindowCardinals(c.FrameWin, NetWMWindowOpacity, values[0])
	} else {
		xproto.DeleteProperty(wm.Conn, c.FrameWin, wm.Atoms.Get(NetWMWindowOpacity))
	}
}

func (wm *WM) updateUserTime(c *Client) {
	if values := wm.getWindowCardinals(c.Win, NetWMUserTimeWindow, 1); len(values) == 1 {
		c.UserTimeWindow = xproto.Window(values[0])
	} else {
		c.UserTimeWindow = xproto.WindowNone
	}
	source := c.Win
	if c.UserTimeWindow != xproto.WindowNone {
		source = c.UserTimeWindow
		wm.selectAdditionalEvents(source, xproto.EventMaskPropertyChange|xproto.EventMaskStructureNotify)
	}
	reply, err := xproto.GetProperty(wm.Conn, false, source, wm.Atoms.Get(NetWMUserTime),
		xproto.AtomCardinal, 0, 1).Reply()
	if err == nil && reply.ValueLen == 1 {
		c.UserTime = getUint32(reply.Value)
	}
}

func (wm *WM) updateFullscreenMonitors(c *Client) {
	values := wm.getWindowCardinals(c.Win, NetWMFullscreenMonitors, 4)
	if len(values) != 4 {
		c.HasFullscreenMonitors = false
		return
	}
	indices := [4]uint32{values[0], values[1], values[2], values[3]}
	if _, _, _, _, ok := fullscreenBounds(wm.monitorSlice(), indices); !ok {
		c.HasFullscreenMonitors = false
		xproto.DeleteProperty(wm.Conn, c.Win, wm.Atoms.Get(NetWMFullscreenMonitors))
		return
	}
	c.FullscreenMonitors = indices
	c.HasFullscreenMonitors = true
	if c.IsFullscreen {
		wm.applyFullscreenGeometry(c)
	}
}

func (wm *WM) updateSyncCounter(c *Client) {
	values := wm.getWindowCardinals(c.Win, NetWMSyncRequestCounter, 1)
	if len(values) == 1 && wm.XSyncAvailable &&
		wm.supportsProtocol(c, wm.Atoms.Get(NetWMSyncRequest)) {
		c.SyncCounter = values[0]
		if value, ok := wm.querySyncCounter(c.SyncCounter); ok {
			c.SyncValue = value
		}
		return
	}
	c.SyncCounter = 0
	c.SyncWaiting = false
	c.SyncPending = false
}

func (wm *WM) syncInteractiveResize(c *Client, x, y, width, height int) bool {
	if c.SyncCounter == 0 || (width == c.W && height == c.H) {
		return false
	}
	if c.SyncWaiting && time.Now().Before(c.SyncDeadline) {
		if value, ok := wm.querySyncCounter(c.SyncCounter); !ok || value < c.SyncValue {
			c.SyncX, c.SyncY, c.SyncW, c.SyncH = x, y, width, height
			c.SyncPending = true
			return true
		}
		c.SyncWaiting = false
	}
	c.SyncValue++
	low, high := splitXSyncValue(c.SyncValue)
	if !wm.sendProtocol(c, wm.Atoms.Get(NetWMSyncRequest), wm.LastUserTime, low, high) {
		c.SyncCounter = 0
		return false
	}
	c.SyncWaiting = true
	c.SyncDeadline = time.Now().Add(time.Second)
	wm.resizeClient(c, x, y, width, height)
	return true
}

func splitXSyncValue(value uint64) (low, high uint32) {
	return uint32(value), uint32(value >> 32)
}

func joinXSyncValue(low, high uint32) uint64 {
	return uint64(high)<<32 | uint64(low)
}

func (wm *WM) recordUserTime(timestamp uint32) {
	if timestamp != 0 && (wm.LastUserTime == 0 || xTimeNotBefore(timestamp, wm.LastUserTime)) {
		wm.LastUserTime = timestamp
	}
}

func (wm *WM) acceptDesktopNames() {
	reply, err := xproto.GetProperty(wm.Conn, false, wm.Root, wm.Atoms.Get(NetDesktopNames),
		wm.Atoms.Get(UTF8String), 0, 4096).Reply()
	if err != nil || reply.ValueLen == 0 {
		return
	}
	names := strings.Split(strings.TrimSuffix(string(reply.Value), "\x00"), "\x00")
	count := max(len(config.Tags), 1)
	wm.DesktopNames = make([]string, count)
	for i := 0; i < count; i++ {
		if i < len(names) && names[i] != "" {
			wm.DesktopNames[i] = names[i]
		} else if i < len(config.Tags) {
			wm.DesktopNames[i] = config.Tags[i]
		}
	}
}

func (wm *WM) SetShowingDesktop(show bool) {
	if wm.ShowingDesktop == show {
		return
	}
	wm.ShowingDesktop = show
	if show {
		wm.ShowDesktopFocus = wm.SelMon.Sel
	}
	wm.setRootCardinals(NetShowingDesktop, boolCardinal(show))
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			wm.publishClientState(c)
		}
	}
	wm.Arrange(nil)
	if show {
		wm.Focus(nil)
	} else if wm.ShowDesktopFocus != nil && wm.clientVisible(wm.ShowDesktopFocus) {
		wm.Focus(wm.ShowDesktopFocus)
		wm.Restack(wm.ShowDesktopFocus.Mon)
	} else {
		wm.Focus(nil)
	}
	if !show {
		wm.ShowDesktopFocus = nil
	}
}

func (wm *WM) checkProtocolTimeouts(now time.Time) {
	wm.refreshMonitorTopology()
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.SyncWaiting {
				value, acknowledged := wm.querySyncCounter(c.SyncCounter)
				if acknowledged && value >= c.SyncValue {
					c.SyncWaiting = false
				} else if !now.Before(c.SyncDeadline) {
					c.SyncWaiting = false
				}
				if !c.SyncWaiting && c.SyncPending {
					x, y, width, height := c.SyncX, c.SyncY, c.SyncW, c.SyncH
					c.SyncPending = false
					wm.syncInteractiveResize(c, x, y, width, height)
				}
			}
			if c.PingPending && !c.Unresponsive && !now.Before(c.PingDeadline) {
				c.Unresponsive = true
				c.DemandsAttention = true
				wm.setUrgent(c, true)
				wm.publishClientState(c)
			}
		}
	}
}

func (wm *WM) refreshMonitorTopology() {
	if wm.Conn == nil || !wm.updateGeom() {
		return
	}
	wm.setRootCardinals(NetDesktopGeometry, uint32(max(wm.SW, 1)), uint32(max(wm.SH, 1)))
	wm.publishWorkareaFromStruts()
	wm.publishSupported()
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.HasFullscreenMonitors {
				wm.updateFullscreenMonitors(c)
			}
			if c.IsFullscreen {
				wm.applyFullscreenGeometry(c)
			}
		}
	}
	wm.Focus(nil)
	wm.Arrange(nil)
}

func boolCardinal(value bool) uint32 {
	if value {
		return 1
	}
	return 0
}
