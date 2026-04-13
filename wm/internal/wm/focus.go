package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// Focus sets focus to client c, or to the top visible client if c is nil.
func (wm *WM) Focus(c *Client) {
	if c == nil || !c.IsVisible() {
		c = nil
		for c = wm.SelMon.Stack; c != nil && !c.IsVisible(); c = c.SNext {
		}
	}

	if wm.SelMon.Sel != nil && wm.SelMon.Sel != c {
		wm.Unfocus(wm.SelMon.Sel, false)
	}

	if c != nil {
		if c.Mon != wm.SelMon {
			wm.SelMon = c.Mon
		}
		if c.IsUrgent {
			wm.setUrgent(c, false)
		}
		wm.detachStack(c)
		wm.attachStack(c)
		wm.GrabButtons(c, true)
		xproto.ChangeWindowAttributes(wm.Conn, c.Win,
			xproto.CwBorderPixel, []uint32{wm.BorderSel})
		wm.setFocus(c)
	} else {
		xproto.SetInputFocus(wm.Conn, xproto.InputFocusPointerRoot,
			wm.Root, xproto.TimeCurrentTime)
		xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetActiveWindow])
	}
	wm.SelMon.Sel = c
	wm.logSelClientInfo()
}

// Unfocus removes focus from client c.
func (wm *WM) Unfocus(c *Client, setFocusToRoot bool) {
	if c == nil {
		return
	}
	wm.GrabButtons(c, false)
	xproto.ChangeWindowAttributes(wm.Conn, c.Win,
		xproto.CwBorderPixel, []uint32{wm.BorderNorm})
	if setFocusToRoot {
		xproto.SetInputFocus(wm.Conn, xproto.InputFocusPointerRoot,
			wm.Root, xproto.TimeCurrentTime)
		xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetActiveWindow])
	}
}

// FocusStack cycles focus through visible clients.
func (wm *WM) FocusStack(arg *config.Arg) {
	if wm.SelMon.Sel == nil || (wm.SelMon.Sel.IsFullscreen && config.LockFullscreen) {
		return
	}

	var c *Client
	if arg.I > 0 {
		// Forward
		for c = wm.SelMon.Sel.Next; c != nil; c = c.Next {
			if c.IsVisible() && !c.IsDock {
				break
			}
		}
		if c == nil {
			for c = wm.SelMon.Clients; c != nil; c = c.Next {
				if c.IsVisible() && !c.IsDock {
					break
				}
			}
		}
	} else {
		// Backward
		var last *Client
		for iter := wm.SelMon.Clients; iter != wm.SelMon.Sel; iter = iter.Next {
			if iter.IsVisible() && !iter.IsDock {
				last = iter
			}
		}
		c = last
		if c == nil {
			for iter := wm.SelMon.Sel; iter != nil; iter = iter.Next {
				if iter.IsVisible() && !iter.IsDock {
					c = iter
				}
			}
		}
	}

	if c != nil {
		wm.Focus(c)
		wm.Restack(wm.SelMon)
	}
}

// FocusUp focuses the client above the current one.
func (wm *WM) FocusUp(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil {
		return
	}
	newc := wm.getUpClient(c)
	if newc != c {
		wm.Focus(newc)
	}
}

// FocusDown focuses the client below the current one.
func (wm *WM) FocusDown(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil {
		return
	}
	newc := wm.getDownClient(c)
	if newc == c {
		newc = wm.getRightClient(c)
	}
	if newc != c {
		wm.Focus(newc)
	}
}

// FocusLeft focuses the client to the left.
func (wm *WM) FocusLeft(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil {
		return
	}
	newc := wm.getLeftClient(c)
	if newc != c {
		wm.Focus(newc)
	}
}

// FocusRight focuses the client to the right.
func (wm *WM) FocusRight(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil {
		return
	}
	newc := wm.getRightClient(c)
	if newc != c {
		wm.Focus(newc)
	}
}

// FocusMon focuses the monitor in the given direction.
func (wm *WM) FocusMon(arg *config.Arg) {
	if wm.Mons.Next == nil {
		return
	}
	m := wm.DirToMon(arg.I)
	if m == wm.SelMon {
		return
	}
	wm.Unfocus(wm.SelMon.Sel, false)
	wm.SelMon = m
	wm.Focus(nil)
}

// Spatial focus helpers

func (wm *WM) getUpClient(c *Client) *Client {
	if wm.onlyClient(c) {
		return c
	}

	best := c
	for iter := wm.NextTiled(wm.SelMon.Clients); iter != nil; iter = wm.NextTiled(iter.Next) {
		if iter == c || !iter.IsVisible() {
			continue
		}
		temp := wm.getDownClient(iter)
		if temp == c {
			best = iter
			break
		}
	}
	return best
}

func (wm *WM) getDownClient(c *Client) *Client {
	targetX := c.X
	targetY := c.Y + c.H + int(config.GapPx) + 2*int(config.BorderPx)

	if wm.onlyClient(c) {
		return c
	}

	best := c
	for iter := wm.NextTiled(wm.SelMon.Clients); iter != nil; iter = wm.NextTiled(iter.Next) {
		if iter == c || !iter.IsVisible() {
			continue
		}
		if iter.X == targetX && iter.Y == targetY {
			best = iter
			break
		}
	}
	return best
}

func (wm *WM) getLeftClient(c *Client) *Client {
	if wm.onlyClient(c) {
		return c
	}

	best := c
	bestYDev := 999999
	for iter := wm.NextTiled(wm.SelMon.Clients); iter != nil; iter = wm.NextTiled(iter.Next) {
		if iter.X >= c.X || !c.IsVisible() {
			continue
		}
		yDev := abs(c.Y - iter.Y)
		if yDev < bestYDev {
			bestYDev = yDev
			best = iter
		}
	}
	return best
}

func (wm *WM) getRightClient(c *Client) *Client {
	if wm.onlyClient(c) {
		return c
	}

	best := c
	bestYDev := 999999
	for iter := wm.NextTiled(wm.SelMon.Clients); iter != nil; iter = wm.NextTiled(iter.Next) {
		if iter == c {
			continue
		}
		if iter.X > c.X {
			yDev := abs(c.Y - iter.Y)
			if yDev < bestYDev {
				bestYDev = yDev
				best = iter
			}
		}
	}
	return best
}

func (wm *WM) setFocus(c *Client) {
	if !c.NeverFocus {
		xproto.SetInputFocus(wm.Conn, xproto.InputFocusPointerRoot,
			c.Win, xproto.TimeCurrentTime)
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
			wm.NetAtom[NetActiveWindow], xproto.AtomWindow, 32, 1,
			uint32ToBytes(uint32(c.Win)))
	}
	wm.sendEvent(c, wm.WMAtom[WMTakeFocus])
}

func (wm *WM) logSelClientInfo() {
	c := wm.SelMon.Sel
	if !wm.Debug {
		return
	}
	if c == nil {
		util.LogDebug("No selected client\n")
	} else {
		util.LogDebugf("Selected client: Name=%s X=%d Y=%d W=%d H=%d", c.Name, c.X, c.Y, c.W, c.H)
	}
}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}
