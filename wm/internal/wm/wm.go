package wm

import (
	"fmt"
	"strings"

	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/xproto"
	"github.com/BurntSushi/xgbutil"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/ipc"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// New creates a new WM instance but does not connect to X yet.
func New() *WM {
	wm := &WM{
		Running:       true,
		ActiveRules:   config.DefaultRules,
		ActiveKeys:    config.DefaultKeys(),
		Layouts:       make([]config.Layout, len(config.DefaultLayouts)),
		MinimizeStack: make([]*Client, 0),
		Actions:       make(map[string]config.ActionFunc),
		TitlebarMap:   make(map[xproto.Window]*Client),
	}
	copy(wm.Layouts, config.DefaultLayouts)
	// Set tile arrange function
	wm.Layouts[config.LayoutTile].Arrange = func(m any) {
		wm.Tile(m.(*Monitor))
	}
	return wm
}

// Setup connects to X11, sets up atoms, cursors, EWMH, and selects events.
func (wm *WM) Setup() {
	var err error

	wm.X, err = xgbutil.NewConn()
	if err != nil {
		util.Die("sadewm: cannot open display: %v", err)
	}
	wm.Conn = wm.X.Conn()

	// Check for another WM
	wm.checkOtherWM()

	setup := xproto.Setup(wm.Conn)
	wm.Screen = &setup.Roots[wm.X.Conn().DefaultScreen]
	wm.Root = wm.Screen.Root
	wm.SW = int(wm.Screen.WidthInPixels)
	wm.SH = int(wm.Screen.HeightInPixels)

	wm.updateGeom()
	wm.internAtoms()
	wm.createCursors()
	wm.allocColors()

	// Create wmcheckwin
	wm.WMCheckWin, _ = xproto.NewWindowId(wm.Conn)
	xproto.CreateWindow(wm.Conn, wm.Screen.RootDepth, wm.WMCheckWin, wm.Root,
		0, 0, 1, 1, 0, xproto.WindowClassInputOutput, wm.Screen.RootVisual, 0, nil)

	// Set _NET_SUPPORTING_WM_CHECK on both root and check window
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.WMCheckWin,
		wm.NetAtom[NetWMCheck], xproto.AtomWindow, 32, 1, uint32ToBytes(uint32(wm.WMCheckWin)))
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.WMCheckWin,
		wm.NetAtom[NetWMName], wm.UTF8, 8, uint32(len("sadewm")), []byte("sadewm"))
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.NetAtom[NetWMCheck], xproto.AtomWindow, 32, 1, uint32ToBytes(uint32(wm.WMCheckWin)))

	// Set _NET_SUPPORTED
	atomData := make([]byte, 4*NetLast)
	for i := 0; i < NetLast; i++ {
		putUint32(atomData[i*4:], uint32(wm.NetAtom[i]))
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.NetAtom[NetSupported], xproto.AtomAtom, 32, uint32(NetLast), atomData)

	// Delete _NET_CLIENT_LIST
	xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetClientList])

	// Select events on root
	xproto.ChangeWindowAttributes(wm.Conn, wm.Root, xproto.CwEventMask|xproto.CwCursor,
		[]uint32{
			xproto.EventMaskSubstructureRedirect |
				xproto.EventMaskSubstructureNotify |
				xproto.EventMaskButtonPress |
				xproto.EventMaskPointerMotion |
				xproto.EventMaskEnterWindow |
				xproto.EventMaskLeaveWindow |
				xproto.EventMaskStructureNotify |
				xproto.EventMaskPropertyChange,
			uint32(wm.Cursors[CurNormal]),
		})

	wm.GrabKeys()
	wm.Focus(nil)

	wm.RegisterActions()
	wm.initXlibDpy()
}

func (wm *WM) checkOtherWM() {
	// Try to select SubstructureRedirect on the root window.
	// If another WM is running, this will fail.
	err := xproto.ChangeWindowAttributesChecked(wm.Conn,
		xproto.Setup(wm.Conn).Roots[wm.Conn.DefaultScreen].Root,
		xproto.CwEventMask,
		[]uint32{xproto.EventMaskSubstructureRedirect}).Check()
	if err != nil {
		util.Die("sadewm: another window manager is already running")
	}
}

func (wm *WM) internAtoms() {
	atomNames := map[int]string{
		NetSupported:                "_NET_SUPPORTED",
		NetWMName:                   "_NET_WM_NAME",
		NetWMState:                  "_NET_WM_STATE",
		NetWMCheck:                  "_NET_SUPPORTING_WM_CHECK",
		NetWMFullscreen:             "_NET_WM_STATE_FULLSCREEN",
		NetActiveWindow:             "_NET_ACTIVE_WINDOW",
		NetWMWindowType:             "_NET_WM_WINDOW_TYPE",
		NetWMStateAbove:             "_NET_WM_STATE_ABOVE",
		NetWMStateStaysOnTop:        "_NET_WM_STATE_STAYS_ON_TOP",
		NetWMWindowTypeDialog:       "_NET_WM_WINDOW_TYPE_DIALOG",
		NetWMWindowTypeDock:         "_NET_WM_WINDOW_TYPE_DOCK",
		NetClientList:               "_NET_CLIENT_LIST",
		NetWMWindowTypeUtility:      "_NET_WM_WINDOW_TYPE_UTILITY",
		NetWMWindowTypeSplash:       "_NET_WM_WINDOW_TYPE_SPLASH",
		NetWMWindowTypeToolbar:      "_NET_WM_WINDOW_TYPE_TOOLBAR",
		NetWMWindowTypePopupMenu:    "_NET_WM_WINDOW_TYPE_POPUP_MENU",
		NetWMWindowTypeDropdownMenu: "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
		NetWMWindowTypeTooltip:      "_NET_WM_WINDOW_TYPE_TOOLTIP",
		NetWMWindowTypeNotification: "_NET_WM_WINDOW_TYPE_NOTIFICATION",
	}
	for idx, name := range atomNames {
		reply, err := xproto.InternAtom(wm.Conn, false, uint16(len(name)), name).Reply()
		if err == nil {
			wm.NetAtom[idx] = reply.Atom
		}
	}

	wmAtomNames := map[int]string{
		WMProtocols: "WM_PROTOCOLS",
		WMDelete:    "WM_DELETE_WINDOW",
		WMState:     "WM_STATE",
		WMTakeFocus: "WM_TAKE_FOCUS",
	}
	for idx, name := range wmAtomNames {
		reply, err := xproto.InternAtom(wm.Conn, false, uint16(len(name)), name).Reply()
		if err == nil {
			wm.WMAtom[idx] = reply.Atom
		}
	}

	reply, err := xproto.InternAtom(wm.Conn, false, uint16(len("UTF8_STRING")), "UTF8_STRING").Reply()
	if err == nil {
		wm.UTF8 = reply.Atom
	}
}

func (wm *WM) createCursors() {
	font, err := xproto.NewFontId(wm.Conn)
	if err != nil {
		return
	}
	xproto.OpenFont(wm.Conn, font, uint16(len("cursor")), "cursor")

	// XC_left_ptr = 68, XC_sizing = 120, XC_fleur = 52
	cursorGlyphs := [CurLast]uint16{68, 120, 52}
	for i := 0; i < CurLast; i++ {
		wm.Cursors[i], _ = xproto.NewCursorId(wm.Conn)
		xproto.CreateGlyphCursor(wm.Conn, wm.Cursors[i], font, font,
			cursorGlyphs[i], cursorGlyphs[i]+1,
			0, 0, 0, 0xFFFF, 0xFFFF, 0xFFFF)
	}
	xproto.CloseFont(wm.Conn, font)
}

func (wm *WM) allocColors() {
	cmap := wm.Screen.DefaultColormap

	normColor := parseColor(config.ColBorderNorm)
	reply, err := xproto.AllocColor(wm.Conn, cmap,
		normColor[0], normColor[1], normColor[2]).Reply()
	if err == nil {
		wm.BorderNorm = reply.Pixel
	}

	selColor := parseColor(config.ColBorderSel)
	reply, err = xproto.AllocColor(wm.Conn, cmap,
		selColor[0], selColor[1], selColor[2]).Reply()
	if err == nil {
		wm.BorderSel = reply.Pixel
	}
}

func parseColor(hex string) [3]uint16 {
	hex = strings.TrimPrefix(hex, "#")
	var r, g, b uint16
	if len(hex) == 6 {
		fmt.Sscanf(hex, "%02x%02x%02x", &r, &g, &b)
		// X11 colors are 16-bit
		r = r * 257
		g = g * 257
		b = b * 257
	}
	return [3]uint16{r, g, b}
}

// xgbEvent bundles an X event with its accompanying protocol error.
type xgbEvent struct {
	ev  xgb.Event
	err xgb.Error
}

// startEventPump starts a goroutine that reads X events from the connection
// and delivers them to wm.XEvCh so the main loop can select between X events
// and IPC requests without ever blocking indefinitely.
func (wm *WM) startEventPump() {
	wm.XEvCh = make(chan xgbEvent, 64)
	go func() {
		for {
			ev, err := wm.Conn.WaitForEvent()
			wm.XEvCh <- xgbEvent{ev, err}
			// A nil ev and nil err signals connection closed.
			if ev == nil && err == nil {
				return
			}
		}
	}()
}

// Run is the main event loop.
func (wm *WM) Run(ipcServer *ipc.Server) {
	var ipcCh <-chan *ipc.IPCRequest

	if ipcServer != nil {
		go ipcServer.Run()
		ipcCh = ipcServer.RequestChan()
	}

	wm.startEventPump()

	for wm.Running {
		// Drain all immediately-available X events before blocking.
	drainX:
		for {
			select {
			case xev := <-wm.XEvCh:
				wm.dispatchXEv(xev)
			default:
				break drainX
			}
		}

		// Block until either an X event or an IPC request arrives.
		if ipcCh != nil {
			select {
			case xev := <-wm.XEvCh:
				wm.dispatchXEv(xev)
			case req := <-ipcCh:
				resp := wm.handleIPCRequest(req)
				req.ResponseCh <- resp
			}
		} else {
			xev := <-wm.XEvCh
			wm.dispatchXEv(xev)
		}

		// After each event, drain any remaining IPC requests (non-blocking).
		if ipcCh != nil {
		drainIPC:
			for {
				select {
				case req := <-ipcCh:
					resp := wm.handleIPCRequest(req)
					req.ResponseCh <- resp
				default:
					break drainIPC
				}
			}
		}
	}
}

func (wm *WM) dispatchXEv(xev xgbEvent) {
	if xev.ev != nil {
		wm.handleEvent(xev.ev)
	}
	if xev.err != nil {
		wm.handleXError(xev.err)
	}
}

func (wm *WM) handleXError(xerr xgb.Error) {
	// Log but don't die — matches C behavior of ignoring most X errors
	util.LogDebugf("X error: %v", xerr)
}

// Scan queries existing windows and manages them.
func (wm *WM) Scan() {
	reply, err := xproto.QueryTree(wm.Conn, wm.Root).Reply()
	if err != nil {
		return
	}

	// First pass: non-transient windows
	for _, win := range reply.Children {
		attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
		if err != nil || attrs.OverrideRedirect {
			continue
		}

		// Check if transient
		prop, err := xproto.GetProperty(wm.Conn, false, win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		if err == nil && prop.ValueLen > 0 {
			continue // handle transients in second pass
		}

		if attrs.MapState == xproto.MapStateViewable || wm.getState(win) == icccmIconicState {
			wm.manage(win, attrs)
		}
	}

	// Second pass: transient windows
	for _, win := range reply.Children {
		attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
		if err != nil {
			continue
		}

		prop, err := xproto.GetProperty(wm.Conn, false, win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		if err != nil || prop.ValueLen == 0 {
			continue
		}

		if attrs.MapState == xproto.MapStateViewable || wm.getState(win) == icccmIconicState {
			wm.manage(win, attrs)
		}
	}
}

const (
	icccmNormalState    = 1
	icccmIconicState    = 3
	icccmWithdrawnState = 0
)

// Startup runs startup commands.
func (wm *WM) Startup() {
	home := util.HomePath()
	if home == "" {
		return
	}

	for _, cmd := range config.StartupCmds() {
		resolved := make([]string, len(cmd))
		for i, s := range cmd {
			resolved[i] = strings.ReplaceAll(s, config.HomeSubStr, home)
		}
		wm.spawnCmd(resolved)
	}
}

// Cleanup tears down the WM.
func (wm *WM) Cleanup() {
	// View all tags
	wm.View(&config.Arg{UI: ^uint32(0)})

	// Set a no-op layout
	noopLayout := config.Layout{Symbol: "", Arrange: nil}
	wm.SelMon.Lt = &noopLayout

	// Unmanage all windows
	for m := wm.Mons; m != nil; m = m.Next {
		for m.Stack != nil {
			wm.unmanage(m.Stack, false)
		}
	}

	// Ungrab keys
	xproto.UngrabKey(wm.Conn, xproto.GrabAny, wm.Root, xproto.ModMaskAny)

	// Free monitors
	wm.Mons = nil

	// Free cursors
	for i := 0; i < CurLast; i++ {
		xproto.FreeCursor(wm.Conn, wm.Cursors[i])
	}

	// Destroy check window
	xproto.DestroyWindow(wm.Conn, wm.WMCheckWin)

	xproto.SetInputFocus(wm.Conn, xproto.InputFocusPointerRoot, xproto.InputFocusPointerRoot, xproto.TimeCurrentTime)
	xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetActiveWindow])
}

// SetTopOffset adjusts the working area of all monitors.
func (wm *WM) SetTopOffset(offset uint) {
	for m := wm.Mons; m != nil; m = m.Next {
		m.WH -= int(offset)
		m.WY += int(offset)
	}
	wm.Arrange(nil)
}

// SetBottomOffset adjusts the working area of all monitors.
func (wm *WM) SetBottomOffset(offset uint) {
	for m := wm.Mons; m != nil; m = m.Next {
		m.WH -= int(offset)
	}
	wm.Arrange(nil)
}

// Helper: uint32 to little-endian bytes
func uint32ToBytes(v uint32) []byte {
	b := make([]byte, 4)
	putUint32(b, v)
	return b
}

func putUint32(b []byte, v uint32) {
	b[0] = byte(v)
	b[1] = byte(v >> 8)
	b[2] = byte(v >> 16)
	b[3] = byte(v >> 24)
}

func getUint32(b []byte) uint32 {
	return uint32(b[0]) | uint32(b[1])<<8 | uint32(b[2])<<16 | uint32(b[3])<<24
}

// handleIPCRequest processes an IPC request from the socket server.
func (wm *WM) handleIPCRequest(req *ipc.IPCRequest) *ipc.Response {
	switch req.Cmd {
	case "get_state":
		return wm.ipcGetState()
	case "tags_state":
		return wm.ipcTagsState()
	case "view":
		wm.View(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "toggleview":
		wm.ToggleView(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "tag":
		wm.Tag(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "toggletag":
		wm.ToggleTag(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "reload":
		wm.ReloadConfig(nil)
		return &ipc.Response{OK: true}
	case "open-launcher":
		wm.spawnCmd([]string{"sadeshell", "--open-launcher"})
		return &ipc.Response{OK: true}
	case "open-emoji-picker":
		wm.spawnCmd([]string{"sadeshell", "--open-emoji-picker"})
		return &ipc.Response{OK: true}
	case "open-window-picker":
		wm.spawnCmd([]string{"sadeshell", "--open-window-picker"})
		return &ipc.Response{OK: true}
	case "get_clients":
		return wm.ipcGetClients()
	case "focus_window":
		return wm.ipcFocusWindow(req.WinID)
	default:
		return &ipc.Response{OK: false, Error: "unknown command"}
	}
}

func (wm *WM) ipcGetState() *ipc.Response {
	resp := &ipc.Response{
		OK:        true,
		TagMask:   wm.SelMon.TagSet[wm.SelMon.SelTags],
		Layout:    wm.SelMon.Lt.Symbol,
		MFact:     float64(wm.SelMon.MFact),
		NMaster:   wm.SelMon.NMaster,
		Gaps:      wm.SelMon.GapPx,
		RightTile: wm.SelMon.IsRightTiled,
		Clients:   []ipc.ClientDTO{},
	}

	for c := wm.SelMon.Clients; c != nil; c = c.Next {
		resp.Clients = append(resp.Clients, ipc.ClientDTO{
			Name:      c.Name,
			WinID:     uint32(c.Win),
			Class:     wm.getWMClass(c.Win),
			Tags:      c.Tags,
			Floating:  c.IsFloating,
			Maximized: c.Maximized,
			Focused:   c == wm.SelMon.Sel,
			Minimized: c.Minimized,
		})
	}

	return resp
}

func (wm *WM) ipcTagsState() *ipc.Response {
	var occ, urg uint32
	for c := wm.SelMon.Clients; c != nil; c = c.Next {
		if c.Tags&TagMask() != TagMask() {
			occ |= c.Tags
			if c.IsUrgent {
				urg |= c.Tags
			}
		}
	}

	states := make([]string, len(config.Tags))
	for i := range config.Tags {
		bit := uint32(1 << i)
		switch {
		case urg&bit != 0:
			states[i] = "U"
		case wm.SelMon.TagSet[wm.SelMon.SelTags]&bit != 0:
			states[i] = "A"
		case occ&bit != 0:
			states[i] = "O"
		default:
			states[i] = "I"
		}
	}

	return &ipc.Response{OK: true, TagsState: states}
}

// ipcGetClients returns all managed clients across all tags (all monitors).
// Dock windows, override-redirect windows, and minimized windows that are
// purely system windows are included only if they pass the IsDock check.
func (wm *WM) ipcGetClients() *ipc.Response {
	clients := []ipc.ClientDTO{}
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.IsDock {
				continue
			}
			clients = append(clients, ipc.ClientDTO{
				Name:      c.Name,
				WinID:     uint32(c.Win),
				Class:     wm.getWMClass(c.Win),
				Tags:      c.Tags,
				Floating:  c.IsFloating,
				Maximized: c.Maximized,
				Focused:   c == m.Sel,
				Minimized: c.Minimized,
			})
		}
	}
	return &ipc.Response{OK: true, Clients: clients}
}

// ipcFocusWindow switches to the tag containing the given window and focuses it.
func (wm *WM) ipcFocusWindow(winID uint32) *ipc.Response {
	if winID == 0 {
		return &ipc.Response{OK: false, Error: "invalid win_id"}
	}
	target := xproto.Window(winID)

	// Find the client across all monitors
	var found *Client
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.Win == target {
				found = c
				break
			}
		}
		if found != nil {
			break
		}
	}

	if found == nil {
		return &ipc.Response{OK: false, Error: "window not found"}
	}

	// Switch selected monitor to the one that owns this client
	if found.Mon != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = found.Mon
	}

	// Switch to the client's tag (use the lowest-numbered tag the client is on)
	clientTags := found.Tags & TagMask()
	if clientTags != 0 {
		// Pick lowest bit tag
		tagMask := clientTags & (^clientTags + 1)
		wm.SelMon.SelTags ^= 1
		wm.SelMon.TagSet[wm.SelMon.SelTags] = tagMask
		wm.ApplyTag(wm.GetDomTag(wm.SelMon.Tags))
	}

	// If minimized, restore it
	if found.Minimized {
		// Remove from minimize stack if present
		for i, mc := range wm.MinimizeStack {
			if mc == found {
				wm.MinimizeStack = append(wm.MinimizeStack[:i], wm.MinimizeStack[i+1:]...)
				break
			}
		}
		found.Minimized = false
		xproto.ConfigureWindow(wm.Conn, found.Win,
			xproto.ConfigWindowX|xproto.ConfigWindowY,
			[]uint32{uint32(found.X), uint32(found.Y)})
		if found.IsFloating {
			wm.showTitlebar(found)
			wm.raiseTitlebar(found)
		}
	}

	wm.Focus(found)
	wm.Restack(found.Mon)
	wm.Arrange(found.Mon)
	return &ipc.Response{OK: true}
}

// getWMClass returns the WM_CLASS string (second part = class name) for a window.
func (wm *WM) getWMClass(w xproto.Window) string {
	reply, err := xproto.GetProperty(wm.Conn, false, w,
		xproto.AtomWmClass, xproto.AtomString, 0, 256).Reply()
	if err != nil || reply.ValueLen == 0 {
		return ""
	}
	parts := splitWMClass(reply.Value)
	if len(parts) >= 2 {
		return parts[1]
	}
	if len(parts) == 1 {
		return parts[0]
	}
	return ""
}
