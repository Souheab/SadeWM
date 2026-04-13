package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
)

// Minimize pushes the selected client onto the minimize stack.
func (wm *WM) Minimize(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil || c.Minimized {
		return
	}
	c.Minimized = true
	wm.MinimizeStack = append(wm.MinimizeStack, c)
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowX, []uint32{uint32(c.Width() * -2)})
	wm.hideTitlebar(c)
	wm.Focus(nil)
	wm.Arrange(wm.SelMon)
}

// Restore pops the last minimized client.
func (wm *WM) Restore(arg *config.Arg) {
	if len(wm.MinimizeStack) == 0 {
		return
	}
	n := len(wm.MinimizeStack)
	c := wm.MinimizeStack[n-1]
	wm.MinimizeStack = wm.MinimizeStack[:n-1]
	c.Minimized = false
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowX|xproto.ConfigWindowY,
		[]uint32{uint32(c.X), uint32(c.Y)})
	wm.Arrange(c.Mon)
	wm.Focus(c)
	wm.Restack(c.Mon)
	if c.IsFloating {
		wm.showTitlebar(c)
		wm.raiseTitlebar(c)
	}
}

// SetFullscreen toggles fullscreen state on a client.
func (wm *WM) SetFullscreen(c *Client, fullscreen bool) {
	if fullscreen && !c.IsFullscreen {
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			wm.NetAtom[NetWMState], xproto.AtomAtom, 32, 1,
			uint32ToBytes(uint32(wm.NetAtom[NetWMFullscreen])))
		c.IsFullscreen = true
		c.OldState = c.IsFloating
		c.OldBW = c.BW
		c.BW = 0
		c.IsFloating = true
		wm.hideTitlebar(c)
		wm.resizeClient(c, c.Mon.MX, c.Mon.MY, c.Mon.MW, c.Mon.MH)
		wm.raiseWindow(c.Win)
	} else if !fullscreen && c.IsFullscreen {
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			wm.NetAtom[NetWMState], xproto.AtomAtom, 32, 0, nil)
		c.IsFullscreen = false
		c.IsFloating = c.OldState
		c.BW = c.OldBW
		c.X = c.OldX
		c.Y = c.OldY
		c.W = c.OldW
		c.H = c.OldH
		wm.resizeClient(c, c.X, c.Y, c.W, c.H)
		if c.IsFloating {
			wm.showTitlebar(c)
		}
		wm.Arrange(c.Mon)
	}
}

// SetAbove toggles the above/always-on-top state.
func (wm *WM) SetAbove(c *Client, above bool) {
	if above && !c.IsAbove {
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			wm.NetAtom[NetWMState], xproto.AtomAtom, 32, 1,
			uint32ToBytes(uint32(wm.NetAtom[NetWMStateAbove])))
		c.IsAbove = true
		wm.raiseWindow(c.Win)
		wm.raiseTitlebar(c)
	} else if !above && c.IsAbove {
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			wm.NetAtom[NetWMState], xproto.AtomAtom, 32, 0, nil)
		c.IsAbove = false
		wm.Arrange(c.Mon)
	}
	wm.drawTitlebar(c)
}

// ToggleFullscr toggles fullscreen on the selected client.
func (wm *WM) ToggleFullscr(arg *config.Arg) {
	if wm.SelMon.Sel != nil {
		wm.SelMon.Sel.Maximized = false
		wm.SetFullscreen(wm.SelMon.Sel, !wm.SelMon.Sel.IsFullscreen)
	}
}

// ToggleMaximize toggles maximize on the selected client.
func (wm *WM) ToggleMaximize(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	wm.SelMon.Sel.Maximized = !wm.SelMon.Sel.Maximized
	if wm.SelMon.Sel.IsFullscreen {
		wm.SetFullscreen(wm.SelMon.Sel, false)
	}
	wm.Arrange(wm.SelMon)
}
