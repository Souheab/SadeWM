package wm

import (
	"os/exec"
	"strings"
	"syscall"

	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// RegisterActions populates the action dispatch table.
func (wm *WM) RegisterActions() {
	wm.Actions = map[string]config.ActionFunc{
		"spawn":          wm.Spawn,
		"focusstack":     wm.FocusStack,
		"focusup":        wm.FocusUp,
		"focusdown":      wm.FocusDown,
		"focusleft":      wm.FocusLeft,
		"focusright":     wm.FocusRight,
		"focusmon":       wm.FocusMon,
		"swapup":         wm.SwapUp,
		"swapdown":       wm.SwapDown,
		"swapleft":       wm.SwapLeft,
		"swapright":      wm.SwapRight,
		"zoom":           wm.Zoom,
		"killclient":     wm.KillClient,
		"minimize":       wm.Minimize,
		"restore":        wm.Restore,
		"view":           wm.View,
		"reloadconfig":   wm.ReloadConfig,
		"viewprev":       wm.ViewPrev,
		"viewnext":       wm.ViewNext,
		"toggleview":     wm.ToggleView,
		"tag":            wm.Tag,
		"toggletag":      wm.ToggleTag,
		"tagmon":         wm.TagMon,
		"setlayout":      wm.SetLayout,
		"setmfact":       wm.SetMFact,
		"setgaps":        wm.SetGaps,
		"incnmaster":     wm.IncNMaster,
		"togglefloating": wm.ToggleFloating,
		"togglefullscr":  wm.ToggleFullscr,
		"togglemaximize": wm.ToggleMaximize,
		"toggletiledir":  wm.ToggleTileDir,
		"layoutnext":     wm.LayoutNext,
		"layoutprev":     wm.LayoutPrev,
		"movemouse":      wm.MoveMouse,
		"resizemouse":    wm.ResizeMouse,
		"quit":           wm.Quit,
	}
}

// Spawn launches a command.
func (wm *WM) Spawn(arg *config.Arg) {
	if arg.V == nil {
		return
	}
	var argv []string
	switch v := arg.V.(type) {
	case []string:
		argv = v
	default:
		return
	}
	wm.spawnCmd(argv)
}

func (wm *WM) spawnCmd(argv []string) {
	if len(argv) == 0 {
		return
	}
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	cmd.Stdin = nil
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		util.LogDebugf("spawn failed: %v", err)
	}
}

// KillClient closes the selected window.
func (wm *WM) KillClient(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil {
		return
	}
	if !wm.sendEvent(c, wm.WMAtom[WMDelete]) {
		xproto.KillClient(wm.Conn, uint32(c.Win))
	}
}

// Quit stops the event loop.
func (wm *WM) Quit(arg *config.Arg) {
	wm.Running = false
}

// SetGaps adjusts gap size.
func (wm *WM) SetGaps(arg *config.Arg) {
	if arg.I == 0 || wm.SelMon.GapPx+arg.I < 0 {
		wm.SelMon.GapPx = 0
	} else {
		wm.SelMon.GapPx += arg.I
	}
	wm.Arrange(wm.SelMon)
}

// SetLayout sets a specific layout.
func (wm *WM) SetLayout(arg *config.Arg) {
	if arg.I >= 0 && arg.I < len(wm.Layouts) {
		wm.SelMon.Lt = &wm.Layouts[arg.I]
	}
	wm.SelMon.LtSymbol = wm.SelMon.Lt.Symbol
	if wm.SelMon.Sel != nil {
		wm.Arrange(wm.SelMon)
	}
}

// SetMFact sets the master area factor.
func (wm *WM) SetMFact(arg *config.Arg) {
	if arg == nil || wm.SelMon.Lt.Arrange == nil {
		return
	}

	f := arg.F
	if wm.SelMon.IsRightTiled {
		f = -f
	}

	if f < 1.0 {
		f += wm.SelMon.MFact
	} else {
		f -= 1.0
	}
	if f < 0.05 || f > 0.95 {
		return
	}

	t := wm.GetDomTag(wm.SelMon.Tags)
	if t != nil {
		t.MFact = f
		wm.SelMon.MFact = t.MFact
	}
	wm.Arrange(wm.SelMon)
}

// IncNMaster adjusts the number of master windows.
func (wm *WM) IncNMaster(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	newN := wm.SelMon.NMaster + arg.I
	if newN < 0 {
		newN = 0
	}
	t.NMaster = newN
	wm.SelMon.NMaster = t.NMaster
	wm.Arrange(wm.SelMon)
}

// ToggleFloating toggles floating state.
func (wm *WM) ToggleFloating(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil || c.IsDock || c.IsFullscreen {
		return
	}
	c.IsFloating = !c.IsFloating || c.IsFixed
	if c.IsFloating {
		wm.Resize(c, c.X, c.Y, c.W, c.H, false)
	}
	wm.Arrange(wm.SelMon)
}

// ToggleTileDir toggles tile direction.
func (wm *WM) ToggleTileDir(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	t.IsRightTiled = !t.IsRightTiled
	wm.ApplyTag(t)
	wm.Arrange(wm.SelMon)
}

// LayoutNext cycles to the next layout.
func (wm *WM) LayoutNext(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	if t.Lt == &wm.Layouts[config.LayoutTile] {
		if !t.IsRightTiled {
			t.IsRightTiled = true
		} else {
			t.Lt = &wm.Layouts[config.LayoutFloat]
		}
	} else {
		t.Lt = &wm.Layouts[config.LayoutTile]
		t.IsRightTiled = false
	}
	wm.ApplyTag(t)
	wm.Arrange(wm.SelMon)
}

// LayoutPrev cycles to the previous layout.
func (wm *WM) LayoutPrev(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	if t.Lt == &wm.Layouts[config.LayoutTile] {
		if t.IsRightTiled {
			t.IsRightTiled = false
		} else {
			t.Lt = &wm.Layouts[config.LayoutFloat]
		}
	} else {
		t.Lt = &wm.Layouts[config.LayoutTile]
		t.IsRightTiled = true
	}
	wm.ApplyTag(t)
	wm.Arrange(wm.SelMon)
}

// Zoom promotes the selected client to master.
func (wm *WM) Zoom(arg *config.Arg) {
	c := wm.SelMon.Sel
	if wm.SelMon.Lt.Arrange == nil || c == nil || c.IsFloating {
		return
	}
	if c == wm.NextTiled(wm.SelMon.Clients) {
		c = wm.NextTiled(c.Next)
		if c == nil {
			return
		}
	}
	wm.pop(c)
}

// SwapClients swaps two clients in the client list.
func (wm *WM) SwapClients(c1, c2 *Client) {
	if c1 == c2 || c1 == nil || c2 == nil {
		return
	}

	var p1, p2 *Client
	for c := wm.SelMon.Clients; c != nil; c = c.Next {
		if c.Next == c1 {
			p1 = c
		}
		if c.Next == c2 {
			p2 = c
		}
	}

	if p1 != nil {
		p1.Next = c2
	} else {
		wm.SelMon.Clients = c2
	}

	if p2 != nil {
		p2.Next = c1
	} else {
		wm.SelMon.Clients = c1
	}

	tmp := c1.Next
	c1.Next = c2.Next
	c2.Next = tmp

	wm.Arrange(wm.SelMon)
}

func (wm *WM) SwapDown(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	wm.SwapClients(wm.SelMon.Sel, wm.getDownClient(wm.SelMon.Sel))
}

func (wm *WM) SwapUp(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	wm.SwapClients(wm.SelMon.Sel, wm.getUpClient(wm.SelMon.Sel))
}

func (wm *WM) SwapLeft(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	wm.SwapClients(wm.SelMon.Sel, wm.getLeftClient(wm.SelMon.Sel))
}

func (wm *WM) SwapRight(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	wm.SwapClients(wm.SelMon.Sel, wm.getRightClient(wm.SelMon.Sel))
}

// TagMon sends the selected client to another monitor.
func (wm *WM) TagMon(arg *config.Arg) {
	if wm.SelMon.Sel == nil || wm.Mons.Next == nil {
		return
	}
	wm.sendMon(wm.SelMon.Sel, wm.DirToMon(arg.I))
}

// sendMon moves a client to another monitor.
func (wm *WM) sendMon(c *Client, m *Monitor) {
	if c.Mon == m || c.IsDock {
		return
	}
	wm.Unfocus(c, true)
	wm.detach(c)
	wm.detachStack(c)
	c.Mon = m
	c.Tags = m.TagSet[m.SelTags]
	wm.attachBottom(c)
	wm.attachStack(c)
	wm.Focus(nil)
	wm.Arrange(nil)
}

// ReloadConfig reloads the TOML config file.
func (wm *WM) ReloadConfig(arg *config.Arg) {
	if wm.CfgPath == "" {
		return
	}

	tc := config.LoadTOML(wm.CfgPath)
	config.ApplyTOML(tc)
	wm.ActiveRules = config.ApplyTOMLRules(tc)
	wm.ActiveKeys = config.MergeKeys(tc, config.DefaultKeys())

	for m := wm.Mons; m != nil; m = m.Next {
		m.GapPx = int(config.GapPx)
		for i := range m.Tags {
			m.Tags[i].MFact = config.MFact
			m.Tags[i].NMaster = config.NMaster
		}

		for c := m.Clients; c != nil; c = c.Next {
			c.BW = int(config.BorderPx)
			xproto.ConfigureWindow(wm.Conn, c.Win,
				xproto.ConfigWindowBorderWidth, []uint32{uint32(c.BW)})
		}

		m.WX = m.MX
		m.WY = m.MY
		m.WW = m.MW
		m.WH = m.MH
		m.WY += int(config.TopOffset)
		m.WH -= int(config.TopOffset) + int(config.BottomOffset)

		wm.Arrange(m)
	}

	xproto.UngrabKey(wm.Conn, xproto.GrabAny, wm.Root, xproto.ModMaskAny)
	wm.GrabKeys()
	wm.Focus(nil)
}

// List operations

func (wm *WM) attach(c *Client) {
	c.Next = c.Mon.Clients
	c.Mon.Clients = c
}

func (wm *WM) attachBottom(c *Client) {
	c.Next = nil
	tc := &c.Mon.Clients
	for *tc != nil {
		tc = &(*tc).Next
	}
	*tc = c
}

func (wm *WM) attachStack(c *Client) {
	c.SNext = c.Mon.Stack
	c.Mon.Stack = c
}

func (wm *WM) detach(c *Client) {
	tc := &c.Mon.Clients
	for *tc != nil && *tc != c {
		tc = &(*tc).Next
	}
	if *tc != nil {
		*tc = c.Next
	}
}

func (wm *WM) detachStack(c *Client) {
	tc := &c.Mon.Stack
	for *tc != nil && *tc != c {
		tc = &(*tc).SNext
	}
	if *tc != nil {
		*tc = c.SNext
	}

	if c == c.Mon.Sel {
		var t *Client
		for t = c.Mon.Stack; t != nil && !t.IsVisible(); t = t.SNext {
		}
		c.Mon.Sel = t
	}
}

func (wm *WM) pop(c *Client) {
	wm.detach(c)
	wm.attach(c)
	wm.Focus(c)
	wm.Arrange(c.Mon)
}

// winToClient finds the client for a given window ID.
func (wm *WM) winToClient(w xproto.Window) *Client {
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.Win == w {
				return c
			}
		}
	}
	return nil
}

func init() {
	_ = util.LogDebug
	_ = strings.ReplaceAll
}
