package wm

import (
	"slices"
	"strings"

	"github.com/jezek/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// EWMH and ICCCM property helpers

func (wm *WM) getAtomProp(c *Client, prop xproto.Atom) xproto.Atom {
	atoms := wm.getWindowAtomProps(c.Win, prop, 1)
	if len(atoms) == 0 {
		return xproto.AtomNone
	}
	return atoms[0]
}

// getAtomProps returns all atoms stored in a property (up to maxN).
func (wm *WM) getAtomProps(c *Client, prop xproto.Atom, maxN uint32) []xproto.Atom {
	return wm.getWindowAtomProps(c.Win, prop, maxN)
}

func (wm *WM) getWindowAtomProps(w xproto.Window, prop xproto.Atom, maxN uint32) []xproto.Atom {
	reply, err := xproto.GetProperty(wm.Conn, false, w, prop,
		xproto.AtomAtom, 0, maxN).Reply()
	if err != nil || reply.ValueLen == 0 {
		return nil
	}
	atoms := make([]xproto.Atom, reply.ValueLen)
	for i := uint32(0); i < reply.ValueLen; i++ {
		atoms[i] = xproto.Atom(getUint32(reply.Value[i*4:]))
	}
	return atoms
}

func atomListContains(atoms []xproto.Atom, atom xproto.Atom) bool {
	for _, a := range atoms {
		if a == atom {
			return true
		}
	}
	return false
}

func atomListAdd(atoms []xproto.Atom, atom xproto.Atom) []xproto.Atom {
	if atom == xproto.AtomNone || atomListContains(atoms, atom) {
		return atoms
	}
	return append(atoms, atom)
}

func atomListRemove(atoms []xproto.Atom, remove ...xproto.Atom) []xproto.Atom {
	out := atoms[:0]
	for _, atom := range atoms {
		if !atomListContains(remove, atom) {
			out = append(out, atom)
		}
	}
	return out
}

func atomsToBytes(atoms []xproto.Atom) []byte {
	data := make([]byte, len(atoms)*4)
	for i, atom := range atoms {
		putUint32(data[i*4:], uint32(atom))
	}
	return data
}

func (wm *WM) setNetWMState(c *Client, states []xproto.Atom) {
	if c.statePublished && slices.Equal(c.publishedState, states) {
		return
	}
	c.publishedState = slices.Clone(states)
	c.statePublished = true
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		wm.Atoms.Get(NetWMState), xproto.AtomAtom, 32, uint32(len(states)), atomsToBytes(states))
}

func (wm *WM) setFrameExtents(c *Client, top uint32) {
	data := make([]byte, 16)
	putUint32(data[8:], top)
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		wm.Atoms.Get(NetFrameExtents), xproto.AtomCardinal, 32, 4, data)
}

func (wm *WM) getState(w xproto.Window) int {
	reply, err := xproto.GetProperty(wm.Conn, false, w,
		wm.Atoms.Get(WMState), wm.Atoms.Get(WMState), 0, 2).Reply()
	if err != nil || reply.ValueLen == 0 {
		return -1
	}
	return int(getUint32(reply.Value))
}

func (wm *WM) getTextProp(w xproto.Window, atom xproto.Atom) string {
	reply, err := xproto.GetProperty(wm.Conn, false, w, atom,
		xproto.AtomAny, 0, 256).Reply()
	if err != nil || reply.ValueLen == 0 {
		return ""
	}
	return string(reply.Value[:reply.ValueLen])
}

func (wm *WM) setClientState(c *Client, state uint32) {
	data := make([]byte, 8)
	putUint32(data[0:], state)
	putUint32(data[4:], uint32(xproto.AtomNone))
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		wm.Atoms.Get(WMState), wm.Atoms.Get(WMState), 32, 2, data)
}

func (wm *WM) sendEvent(c *Client, proto xproto.Atom) bool {
	return wm.sendProtocol(c, proto, wm.LastUserTime, 0, 0)
}

func (wm *WM) supportsProtocol(c *Client, proto xproto.Atom) bool {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		wm.Atoms.Get(WMProtocols), xproto.AtomAtom, 0, 32).Reply()
	if err != nil || reply.ValueLen == 0 {
		return false
	}

	exists := false
	for i := uint32(0); i < reply.ValueLen; i++ {
		a := xproto.Atom(getUint32(reply.Value[i*4:]))
		if a == proto {
			exists = true
			break
		}
	}

	return exists
}

func (wm *WM) sendProtocol(c *Client, proto xproto.Atom, timestamp, data2, data3 uint32) bool {
	if !wm.supportsProtocol(c, proto) {
		return false
	}
	if timestamp == 0 {
		timestamp = uint32(xproto.TimeCurrentTime)
	}
	{
		data := xproto.ClientMessageDataUnionData32New([]uint32{
			uint32(proto),
			timestamp,
			data2, data3, 0,
		})
		ev := xproto.ClientMessageEvent{
			Format: 32,
			Window: c.Win,
			Type:   wm.Atoms.Get(WMProtocols),
			Data:   data,
		}
		xproto.SendEvent(wm.Conn, false, c.Win, xproto.EventMaskNoEvent, string(ev.Bytes()))
	}
	return true
}

// updateWindowType checks EWMH window type and state atoms.
func (wm *WM) updateWindowType(c *Client) {
	wtypes := wm.getAtomProps(c, wm.Atoms.Get(NetWMWindowType), 32)
	c.WindowType = wm.Atoms.Get(NetWMWindowTypeNormal)
	for _, wtype := range wtypes {
		if wm.isKnownWindowType(wtype) {
			c.WindowType = wtype
			break
		}
	}
	c.IsDesktop = c.WindowType == wm.Atoms.Get(NetWMWindowTypeDesktop)
	c.IsDock = c.WindowType == wm.Atoms.Get(NetWMWindowTypeDock)
	c.TypeNeverFocus = false
	if c.IsDesktop || c.IsDock {
		c.IsFloating = true
		c.Tags = TagMask()
		c.TypeNeverFocus = true
		c.SkipTaskbar = true
		c.SkipPager = true
		c.BW = 0
		wm.destroyTitlebar(c)
	}
	switch c.WindowType {
	case wm.Atoms.Get(NetWMWindowTypeTooltip), wm.Atoms.Get(NetWMWindowTypeNotification),
		wm.Atoms.Get(NetWMWindowTypePopupMenu), wm.Atoms.Get(NetWMWindowTypeDropdownMenu),
		wm.Atoms.Get(NetWMWindowTypeCombo), wm.Atoms.Get(NetWMWindowTypeDND),
		wm.Atoms.Get(NetWMWindowTypeSplash), wm.Atoms.Get(NetWMWindowTypeMenu):
		c.TypeNeverFocus = true
		c.SkipTaskbar = true
		c.SkipPager = true
	}
	if wm.hasFloatingWindowType(wtypes) {
		c.IsFloating = true
	}
	c.NeverFocus = c.TypeNeverFocus || c.InputNeverFocus
	wm.publishAllowedActions(c)
}

func (wm *WM) isKnownWindowType(atom xproto.Atom) bool {
	for _, name := range []AtomName{NetWMWindowTypeDesktop, NetWMWindowTypeDock,
		NetWMWindowTypeToolbar, NetWMWindowTypeMenu, NetWMWindowTypeUtility,
		NetWMWindowTypeSplash, NetWMWindowTypeDialog, NetWMWindowTypeDropdownMenu,
		NetWMWindowTypePopupMenu, NetWMWindowTypeTooltip, NetWMWindowTypeNotification,
		NetWMWindowTypeCombo, NetWMWindowTypeDND, NetWMWindowTypeNormal} {
		if atom == wm.Atoms.Get(name) {
			return true
		}
	}
	return false
}

// isFloatingWindowType returns true for window types that should be floating.
func (wm *WM) isFloatingWindowType(wtype xproto.Atom) bool {
	if wtype == xproto.AtomNone {
		return false
	}
	return wtype == wm.Atoms.Get(NetWMWindowTypeDialog) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeUtility) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeSplash) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeToolbar) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeMenu) ||
		wtype == wm.Atoms.Get(NetWMWindowTypePopupMenu) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeDropdownMenu) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeTooltip) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeNotification) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeCombo) ||
		wtype == wm.Atoms.Get(NetWMWindowTypeDND)
}

func (wm *WM) hasFloatingWindowType(wtypes []xproto.Atom) bool {
	for _, wtype := range wtypes {
		if wm.isFloatingWindowType(wtype) {
			return true
		}
	}
	return false
}

// updateSizeHints reads ICCCM size hints.
func (wm *WM) updateSizeHints(c *Client) {
	c.HasPositionHint = false

	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmNormalHints, xproto.AtomWmSizeHints, 0, 18).Reply()
	if err != nil || reply.ValueLen < 18 {
		return
	}

	v := reply.Value
	flags := getUint32(v[0:])
	const (
		usPosition  = 1 << 0
		pPosition   = 1 << 2
		pMinSize    = 1 << 4
		pMaxSize    = 1 << 5
		pResizeInc  = 1 << 6
		pBaseSize   = 1 << 8
		pAspect     = 1 << 7
		pWinGravity = 1 << 9
	)

	c.HasPositionHint = flags&(usPosition|pPosition) != 0

	if flags&pBaseSize != 0 {
		c.BaseW = int(getUint32(v[60:]))
		c.BaseH = int(getUint32(v[64:]))
	} else if flags&pMinSize != 0 {
		c.BaseW = int(getUint32(v[20:]))
		c.BaseH = int(getUint32(v[24:]))
	} else {
		c.BaseW = 0
		c.BaseH = 0
	}

	if flags&pResizeInc != 0 {
		c.IncW = int(getUint32(v[36:]))
		c.IncH = int(getUint32(v[40:]))
	} else {
		c.IncW = 0
		c.IncH = 0
	}

	if flags&pMaxSize != 0 {
		c.MaxW = int(getUint32(v[28:]))
		c.MaxH = int(getUint32(v[32:]))
	} else {
		c.MaxW = 0
		c.MaxH = 0
	}

	if flags&pMinSize != 0 {
		c.MinW = int(getUint32(v[20:]))
		c.MinH = int(getUint32(v[24:]))
	} else if flags&pBaseSize != 0 {
		c.MinW = int(getUint32(v[60:]))
		c.MinH = int(getUint32(v[64:]))
	} else {
		c.MinW = 0
		c.MinH = 0
	}

	if flags&pAspect != 0 {
		minAspX := int(getUint32(v[44:]))
		minAspY := int(getUint32(v[48:]))
		maxAspX := int(getUint32(v[52:]))
		maxAspY := int(getUint32(v[56:]))
		if minAspX > 0 {
			c.MinA = float32(minAspY) / float32(minAspX)
		}
		if maxAspY > 0 {
			c.MaxA = float32(maxAspX) / float32(maxAspY)
		}
	} else {
		c.MinA = 0
		c.MaxA = 0
	}

	c.IsFixed = c.MaxW > 0 && c.MaxH > 0 && c.MaxW == c.MinW && c.MaxH == c.MinH
	c.WinGravity = xproto.GravityNorthWest
	if flags&pWinGravity != 0 {
		c.WinGravity = byte(getUint32(v[68:]))
	}
	c.HintsValid = true
}

func (wm *WM) updateColormapWindows(c *Client) {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win, wm.Atoms.Get(WMColormapWindows),
		xproto.AtomWindow, 0, 256).Reply()
	c.ColormapWindows = c.ColormapWindows[:0]
	if err == nil {
		for i := uint32(0); i < reply.ValueLen; i++ {
			win := xproto.Window(getUint32(reply.Value[i*4:]))
			c.ColormapWindows = append(c.ColormapWindows, win)
			wm.selectAdditionalEvents(win, xproto.EventMaskColorMapChange|xproto.EventMaskStructureNotify)
		}
	}
	if len(c.ColormapWindows) == 0 {
		c.ColormapWindows = append(c.ColormapWindows, c.Win)
	}
}

func (wm *WM) selectAdditionalEvents(win xproto.Window, mask uint32) {
	attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
	if err != nil {
		return
	}
	xproto.ChangeWindowAttributes(wm.Conn, win, xproto.CwEventMask,
		[]uint32{attrs.YourEventMask | mask})
}

func (wm *WM) installClientColormaps(c *Client) {
	for i := len(c.ColormapWindows) - 1; i >= 0; i-- {
		if attrs, err := xproto.GetWindowAttributes(wm.Conn, c.ColormapWindows[i]).Reply(); err == nil &&
			attrs.Colormap != xproto.ColormapNone {
			xproto.InstallColormap(wm.Conn, attrs.Colormap)
		}
	}
}

func (wm *WM) clientForColormapWindow(win xproto.Window) *Client {
	if c := wm.winToClient(win); c != nil {
		return c
	}
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			for _, candidate := range c.ColormapWindows {
				if candidate == win {
					return c
				}
			}
		}
	}
	return nil
}

// updateWMHints reads ICCCM WM_HINTS.
func (wm *WM) updateWMHints(c *Client) {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 0, 9).Reply()
	if err != nil || reply.ValueLen == 0 {
		c.InputNeverFocus = false
		c.NeverFocus = c.TypeNeverFocus
		c.IsUrgent = false
		c.WindowGroup = xproto.WindowNone
		return
	}

	v := reply.Value
	flags := getUint32(v[0:])

	const (
		inputHint       = 1 << 0
		stateHint       = 1 << 1
		windowGroupHint = 1 << 6
		urgencyHint     = 1 << 8
	)

	if c == wm.SelMon.Sel && flags&urgencyHint != 0 {
		// Clear urgency for focused window
		c.IsUrgent = false
		flags &^= urgencyHint
		putUint32(v[0:], flags)
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			xproto.AtomWmHints, xproto.AtomWmHints, 32, reply.ValueLen, v)
	} else {
		c.IsUrgent = flags&urgencyHint != 0
	}

	if flags&inputHint != 0 {
		c.InputNeverFocus = getUint32(v[4:]) == 0
	} else {
		c.InputNeverFocus = false
	}
	c.NeverFocus = c.TypeNeverFocus || c.InputNeverFocus
	if flags&windowGroupHint != 0 && reply.ValueLen >= 9 {
		c.WindowGroup = xproto.Window(getUint32(v[32:]))
	}
	if flags&stateHint != 0 && reply.ValueLen >= 3 && getUint32(v[8:]) == icccmIconicState {
		c.InitialIconic = true
	} else {
		c.InitialIconic = false
	}
}

// updateTitle reads the window title.
func (wm *WM) updateTitle(c *Client) {
	name := wm.getTextProp(c.Win, wm.Atoms.Get(NetWMName))
	if name == "" {
		name = wm.getTextProp(c.Win, xproto.AtomWmName)
	}
	if name == "" {
		name = "broken"
	}
	c.Name = name
}

// updateClientList rebuilds _NET_CLIENT_LIST.
func (wm *WM) updateClientList() {
	mapping := make([]uint32, len(wm.ManageOrder))
	for i, c := range wm.ManageOrder {
		mapping[i] = uint32(c.Win)
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.Atoms.Get(NetClientList), xproto.AtomWindow, 32, uint32(len(mapping)), uint32sToBytes(mapping))
	wm.stackingDirty = true
}

func uint32sToBytes(values []uint32) []byte {
	data := make([]byte, len(values)*4)
	for i, value := range values {
		putUint32(data[i*4:], value)
	}
	return data
}

func (wm *WM) setRootCardinals(name AtomName, values ...uint32) {
	if wm.Conn == nil {
		return
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.Atoms.Get(name), xproto.AtomCardinal, 32, uint32(len(values)), uint32sToBytes(values))
}

func (wm *WM) setWindowCardinals(win xproto.Window, name AtomName, values ...uint32) {
	if wm.Conn == nil {
		return
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, win,
		wm.Atoms.Get(name), xproto.AtomCardinal, 32, uint32(len(values)), uint32sToBytes(values))
}

func (wm *WM) setWindowUTF8(win xproto.Window, name AtomName, value string) {
	if wm.Conn == nil {
		return
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, win,
		wm.Atoms.Get(name), wm.Atoms.Get(UTF8String), 8, uint32(len(value)), []byte(value))
}

func (wm *WM) setRootWindow(name AtomName, win xproto.Window) {
	if wm.Conn == nil {
		return
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.Atoms.Get(name), xproto.AtomWindow, 32, 1, uint32ToBytes(uint32(win)))
}

func (wm *WM) publishSupported() {
	atoms := make([]xproto.Atom, 0, len(supportedAtomNames)+3)
	for _, name := range supportedAtomNames {
		atoms = append(atoms, wm.Atoms.Get(name))
	}
	if wm.XineramaAvailable {
		atoms = append(atoms, wm.Atoms.Get(NetWMFullscreenMonitors))
	}
	if wm.XSyncAvailable {
		atoms = append(atoms, wm.Atoms.Get(NetWMSyncRequest), wm.Atoms.Get(NetWMSyncRequestCounter))
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.Atoms.Get(NetSupported), xproto.AtomAtom, 32, uint32(len(atoms)), atomsToBytes(atoms))
}

func highestTagIndex(mask uint32) uint32 {
	mask &= TagMask()
	var result uint32
	for i := range config.Tags {
		if mask&(1<<uint(i)) != 0 {
			result = uint32(i)
		}
	}
	return result
}

func desktopForTags(tags uint32) uint32 {
	if tags&TagMask() == TagMask() {
		return ^uint32(0)
	}
	return highestTagIndex(tags)
}

func (wm *WM) currentDesktop() uint32 {
	if wm.SelMon == nil {
		return 0
	}
	return highestTagIndex(wm.SelMon.TagSet[wm.SelMon.SelTags])
}

func (wm *WM) publishDesktopProperties() {
	count := len(config.Tags)
	if count == 0 {
		count = 1
	}
	wm.DesktopNames = append(wm.DesktopNames[:0], config.Tags...)
	wm.setRootCardinals(NetNumberOfDesktops, uint32(count))
	wm.setRootCardinals(NetDesktopGeometry, uint32(max(wm.SW, 1)), uint32(max(wm.SH, 1)))
	viewport := make([]uint32, count*2)
	wm.setRootCardinals(NetDesktopViewport, viewport...)
	wm.setRootCardinals(NetCurrentDesktop, wm.currentDesktop())
	wm.setRootCardinals(NetShowingDesktop, 0)
	wm.publishDesktopNames()
	wm.publishWorkarea()
	wm.setRootWindow(NetActiveWindow, xproto.WindowNone)
}

func (wm *WM) publishDesktopNames() {
	names := strings.Join(wm.DesktopNames, "\x00") + "\x00"
	wm.setWindowUTF8(wm.Root, NetDesktopNames, names)
}

func (wm *WM) publishCurrentDesktop() {
	wm.setRootCardinals(NetCurrentDesktop, wm.currentDesktop())
}

func (wm *WM) publishClientDesktop(c *Client) {
	wm.setWindowCardinals(c.Win, NetWMDesktop, desktopForTags(c.Tags))
}

func (wm *WM) publishWorkarea() {
	count := max(len(config.Tags), 1)
	values := make([]uint32, 0, count*4)
	for range count {
		x, y := 0, int(wm.TopOffset)
		w := max(wm.SW, 1)
		h := max(wm.SH-y-int(wm.BottomOffset), 1)
		values = append(values, uint32(x), uint32(y), uint32(w), uint32(h))
	}
	wm.setRootCardinals(NetWorkarea, values...)
}

func (wm *WM) publishAllowedActions(c *Client) {
	actions := []xproto.Atom{}
	if !c.IsDock && !c.IsDesktop {
		actions = append(actions, wm.Atoms.Get(NetWMActionClose))
		actions = append(actions,
			wm.Atoms.Get(NetWMActionMove), wm.Atoms.Get(NetWMActionMinimize),
			wm.Atoms.Get(NetWMActionShade), wm.Atoms.Get(NetWMActionStick),
			wm.Atoms.Get(NetWMActionFullscreen), wm.Atoms.Get(NetWMActionChangeDesktop),
			wm.Atoms.Get(NetWMActionAbove), wm.Atoms.Get(NetWMActionBelow))
		if !c.IsFixed {
			actions = append(actions, wm.Atoms.Get(NetWMActionResize),
				wm.Atoms.Get(NetWMActionMaximizeHorz), wm.Atoms.Get(NetWMActionMaximizeVert))
		}
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		wm.Atoms.Get(NetWMAllowedActions), xproto.AtomAtom, 32, uint32(len(actions)), atomsToBytes(actions))
}

func (wm *WM) publishClientState(c *Client) {
	states := make([]xproto.Atom, 0, 12)
	add := func(on bool, name AtomName) {
		if on {
			states = append(states, wm.Atoms.Get(name))
		}
	}
	add(c.IsModal, NetWMStateModal)
	add(c.IsSticky, NetWMStateSticky)
	add(c.MaximizedVert, NetWMStateMaximizedVert)
	add(c.MaximizedHorz, NetWMStateMaximizedHorz)
	add(c.IsShaded, NetWMStateShaded)
	add(c.SkipTaskbar, NetWMStateSkipTaskbar)
	add(c.SkipPager, NetWMStateSkipPager)
	add(c.Minimized || (wm.ShowingDesktop && !c.IsDock && !c.IsDesktop), NetWMStateHidden)
	add(c.IsFullscreen, NetWMFullscreen)
	add(c.IsAbove, NetWMStateAbove)
	add(c.IsBelow, NetWMStateBelow)
	add(c.DemandsAttention, NetWMStateDemandsAttention)
	add(wm.Focused == c, NetWMStateFocused)
	wm.setNetWMState(c, states)
}

// Invalidate now; publish once at the end of an event batch.
func (wm *WM) updateClientListStacking() { wm.stackingDirty = true }

func (wm *WM) flushClientListStacking() {
	if !wm.stackingDirty {
		return
	}
	wm.stackingDirty = false
	clients := wm.ManageOrder
	stacking := make([]uint32, 0, len(clients))
	seen := make(map[*Client]bool, len(clients))
	if tree, err := xproto.QueryTree(wm.Conn, wm.Root).Reply(); err == nil {
		for _, win := range tree.Children {
			c := wm.winToClient(win)
			if c == nil {
				c = wm.FrameMap[win]
			}
			if c != nil && !seen[c] {
				stacking = append(stacking, uint32(c.Win))
				seen[c] = true
			}
		}
	}
	for _, c := range clients {
		if !seen[c] {
			stacking = append(stacking, uint32(c.Win))
		}
	}
	if wm.stackingPublished && slices.Equal(wm.lastStacking, stacking) {
		return
	}
	wm.lastStacking = slices.Clone(stacking)
	wm.stackingPublished = true
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.Atoms.Get(NetClientListStacking), xproto.AtomWindow, 32, uint32(len(stacking)), uint32sToBytes(stacking))
}

// setUrgent sets the urgency hint on a window.
func (wm *WM) setUrgent(c *Client, urg bool) {
	c.IsUrgent = urg
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 0, 9).Reply()
	if err != nil {
		return
	}

	const urgencyHint = 1 << 8
	v := reply.Value
	valueLen := reply.ValueLen
	if valueLen == 0 {
		if !urg {
			return
		}
		// A rejected activation must set ICCCM urgency even when the client did
		// not create WM_HINTS. Publish a complete zero-initialized hints value
		// with only the urgency bit set.
		v = make([]byte, 9*4)
		valueLen = 9
	}
	flags := getUint32(v[0:])
	if urg {
		flags |= urgencyHint
	} else {
		flags &^= urgencyHint
	}
	putUint32(v[0:], flags)
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 32, valueLen, v)
}

func init() {
	_ = util.LogDebug
	_ = config.Tags
}

func (wm *WM) updateWMClass(c *Client) {
	c.Class, c.Instance = "", ""
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win, xproto.AtomWmClass, xproto.AtomString, 0, 256).Reply()
	if err != nil || reply == nil {
		return
	}
	parts := splitWMClass(reply.Value)
	if len(parts) > 0 {
		c.Instance = parts[0]
		c.Class = parts[0]
	}
	if len(parts) > 1 {
		c.Class = parts[1]
	}
}
