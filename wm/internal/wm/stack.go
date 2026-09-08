package wm

import (
	"github.com/jezek/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
)

// Minimize pushes the selected client onto the minimize stack.
func (wm *WM) Minimize(arg *config.Arg) {
	c := wm.SelMon.Sel
	wm.minimizeClient(c)
}

func (wm *WM) minimizeClient(c *Client) {
	if c == nil || c.Minimized || c.IsDock || c.IsDesktop {
		return
	}
	c.Minimized = true
	wm.MinimizeStack = append(wm.MinimizeStack, c)
	if c.FrameWin != 0 {
		c.IgnoreUnmap += 3
	} else {
		c.IgnoreUnmap += 2
	}
	xproto.UnmapWindow(wm.Conn, c.Win)
	if c.FrameWin != 0 {
		xproto.UnmapWindow(wm.Conn, c.FrameWin)
	}
	wm.hideBorderWindow(c)
	wm.setClientState(c, icccmIconicState)
	wm.publishClientState(c)
	wm.Focus(nil)
	wm.Arrange(c.Mon)
}

// Restore pops the last minimized client.
func (wm *WM) Restore(arg *config.Arg) {
	if len(wm.MinimizeStack) == 0 {
		return
	}
	n := len(wm.MinimizeStack)
	c := wm.MinimizeStack[n-1]
	wm.restoreClient(c)
}

func (wm *WM) restoreClient(c *Client) {
	if c == nil || !c.Minimized {
		return
	}
	for i := len(wm.MinimizeStack) - 1; i >= 0; i-- {
		if wm.MinimizeStack[i] == c {
			wm.MinimizeStack = append(wm.MinimizeStack[:i], wm.MinimizeStack[i+1:]...)
		}
	}
	c.Minimized = false
	c.HasMapped = true
	wm.setClientState(c, icccmNormalState)
	xproto.MapWindow(wm.Conn, c.Win)
	if c.FrameWin != 0 {
		xproto.MapWindow(wm.Conn, c.FrameWin)
		wm.showTitlebar(c)
	}
	wm.publishClientState(c)
	wm.forwardWindowOpacity(c)
	wm.Focus(c)
	wm.Arrange(c.Mon)
	if c.IsFloating {
		wm.showTitlebar(c)
		wm.raiseTitlebar(c)
	}
}

// SetFullscreen toggles fullscreen state on a client.
func (wm *WM) SetFullscreen(c *Client, fullscreen bool) {
	if fullscreen && !c.IsFullscreen {
		c.rememberFullscreenGeometry()
		c.IsFullscreen = true
		c.OldState = c.IsFloating
		c.OldBW = c.BW
		c.BW = 0
		c.IsFloating = true
		if c.IsShaded {
			xproto.MapWindow(wm.Conn, c.Win)
		}
		wm.destroyBorderWindow(c)
		wm.destroyTitlebar(c)
		// Grab pointer so EnterNotify events from the resize get Mode=WhileGrabbed
		// and are ignored by handleEnterNotify, preventing focus-follows-mouse
		// from stealing focus during the geometry change.
		if !wm.dragging {
			xproto.GrabPointerUnchecked(wm.Conn, false, wm.Root, 0,
				xproto.GrabModeAsync, xproto.GrabModeAsync,
				xproto.WindowNone, xproto.CursorNone, xproto.TimeCurrentTime)
		}
		wm.applyFullscreenGeometry(c)
		wm.raiseWindow(wm.stackWindow(c))
		if !wm.dragging {
			xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
		}
	} else if !fullscreen && c.IsFullscreen {
		c.IsFullscreen = false
		c.IsFloating = c.OldState
		c.BW = c.OldBW
		x, y, width, height := c.fullscreenRestoreGeometry()
		if !wm.dragging {
			xproto.GrabPointerUnchecked(wm.Conn, false, wm.Root, 0,
				xproto.GrabModeAsync, xproto.GrabModeAsync,
				xproto.WindowNone, xproto.CursorNone, xproto.TimeCurrentTime)
		}
		wm.resizeClient(c, x, y, width, height)
		c.FullscreenRestoreValid = false
		if c.MaximizedHorz || c.MaximizedVert {
			wm.setMaximizedAxes(c, c.MaximizedHorz, c.MaximizedVert)
		}
		if c.IsShaded {
			// Re-apply the titlebar-only presentation without changing the
			// preserved SHADED state.
			c.IsShaded = false
			wm.setShaded(c, true)
		}
		wm.Arrange(c.Mon)
		if !wm.dragging {
			xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
		}
	}
	wm.publishClientState(c)
	wm.publishAllowedActions(c)
}

func (wm *WM) applyFullscreenGeometry(c *Client) {
	x, y, width, height := c.Mon.MX, c.Mon.MY, c.Mon.MW, c.Mon.MH
	if c.HasFullscreenMonitors {
		if sx, sy, sw, sh, ok := fullscreenBounds(wm.monitorSlice(), c.FullscreenMonitors); ok {
			x, y, width, height = sx, sy, sw, sh
		}
	}
	wm.resizeClient(c, x, y, width, height)
}

func fullscreenBounds(monitors []*Monitor, indices [4]uint32) (x, y, width, height int, ok bool) {
	t, b, l, r := indices[0], indices[1], indices[2], indices[3]
	if int(t) >= len(monitors) || int(b) >= len(monitors) || int(l) >= len(monitors) || int(r) >= len(monitors) {
		return 0, 0, 0, 0, false
	}
	x = monitors[l].MX
	y = monitors[t].MY
	width = monitors[r].MX + monitors[r].MW - x
	height = monitors[b].MY + monitors[b].MH - y
	return x, y, width, height, width > 0 && height > 0
}

// SetAbove toggles the above/always-on-top state.
func (wm *WM) SetAbove(c *Client, above bool) {
	if above && !c.IsAbove {
		c.IsAbove = true
		c.IsBelow = false
		wm.raiseWindow(wm.stackWindow(c))
		wm.restackBorderWindow(c)
	} else if !above && c.IsAbove {
		c.IsAbove = false
		wm.Arrange(c.Mon)
	}
	wm.publishClientState(c)
	wm.drawTitlebar(c)
}

// ToggleFullscr toggles fullscreen on the selected client.
func (wm *WM) ToggleFullscr(arg *config.Arg) {
	if wm.SelMon.Sel != nil {
		wm.SetFullscreen(wm.SelMon.Sel, !wm.SelMon.Sel.IsFullscreen)
	}
}

// ToggleMaximize toggles maximize on the selected client.
func (wm *WM) ToggleMaximize(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	c := wm.SelMon.Sel
	maximized := !(c.MaximizedHorz && c.MaximizedVert)
	if wm.SelMon.Sel.IsFullscreen {
		wm.SetFullscreen(wm.SelMon.Sel, false)
	}
	wm.setMaximizedAxes(c, maximized, maximized)
	// Grab pointer so EnterNotify events from the layout change get
	// Mode=WhileGrabbed and are ignored by handleEnterNotify.
	if !wm.dragging {
		xproto.GrabPointerUnchecked(wm.Conn, false, wm.Root, 0,
			xproto.GrabModeAsync, xproto.GrabModeAsync,
			xproto.WindowNone, xproto.CursorNone, xproto.TimeCurrentTime)
	}
	wm.Arrange(wm.SelMon)
	if !wm.dragging {
		xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
	}
	wm.publishClientState(c)
}
