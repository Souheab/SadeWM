package wm

import "github.com/jezek/xgb/xproto"

func (wm *WM) usesBorderFrame(c *Client) bool {
	return c != nil && c.BW > 0 && !c.IsDock && !c.IsFloating && !c.IsFullscreen &&
		c.Mon != nil && c.Mon.Lt.Arrange != nil
}

func (wm *WM) borderGeom(c *Client) (x, y, w, h int) {
	x = c.X - c.BW
	y = c.Y - c.BW
	w = c.W + 2*c.BW
	h = c.H + 2*c.BW
	if w < 1 {
		w = 1
	}
	if h < 1 {
		h = 1
	}
	return
}

func (wm *WM) borderPixelFor(c *Client) uint32 {
	if c != nil && c.Mon != nil && c == c.Mon.Sel {
		return wm.BorderSel
	}
	return wm.BorderNorm
}

func (wm *WM) paintBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	xproto.ClearArea(wm.Conn, false, c.BorderWin, 0, 0, 0, 0)
}

func (wm *WM) setBorderWindowColor(c *Client, pixel uint32) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	xproto.ChangeWindowAttributes(wm.Conn, c.BorderWin, xproto.CwBackPixel, []uint32{pixel})
	wm.paintBorderWindow(c)
}

func (wm *WM) createBorderWindow(c *Client) {
	if c == nil || c.BorderWin != 0 || !wm.usesBorderFrame(c) {
		return
	}

	win, err := xproto.NewWindowId(wm.Conn)
	if err != nil {
		return
	}
	x, y, w, h := wm.borderGeom(c)
	mask := uint32(xproto.CwBackPixel | xproto.CwOverrideRedirect)
	vals := []uint32{wm.borderPixelFor(c), 1}
	xproto.CreateWindow(wm.Conn, 0,
		win, wm.Root,
		int16(x), int16(y), uint16(w), uint16(h),
		0,
		xproto.WindowClassInputOutput,
		xproto.WindowNone,
		mask, vals)
	c.BorderWin = win
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowBorderWidth, []uint32{0})
	wm.moveBorderWindow(c)
	wm.restackBorderWindow(c)
}

func (wm *WM) destroyBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	xproto.DestroyWindow(wm.Conn, c.BorderWin)
	c.BorderWin = 0
}

func (wm *WM) ensureBorderWindow(c *Client) {
	if !wm.usesBorderFrame(c) {
		wm.destroyBorderWindow(c)
		return
	}
	if c.BorderWin == 0 {
		wm.createBorderWindow(c)
		return
	}
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowBorderWidth, []uint32{0})
	wm.moveBorderWindow(c)
	wm.setBorderWindowColor(c, wm.borderPixelFor(c))
	wm.restackBorderWindow(c)
}

func (wm *WM) moveBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	x, y, w, h := wm.borderGeom(c)
	xproto.ConfigureWindow(wm.Conn, c.BorderWin,
		xproto.ConfigWindowX|xproto.ConfigWindowY|
			xproto.ConfigWindowWidth|xproto.ConfigWindowHeight,
		[]uint32{uint32(x), uint32(y), uint32(w), uint32(h)})
}

func (wm *WM) showBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	wm.moveBorderWindow(c)
	xproto.MapWindow(wm.Conn, c.BorderWin)
	wm.paintBorderWindow(c)
}

func (wm *WM) hideBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	xproto.UnmapWindow(wm.Conn, c.BorderWin)
}

func (wm *WM) restackBorderWindow(c *Client) {
	if c == nil || c.BorderWin == 0 {
		return
	}
	xproto.ConfigureWindow(wm.Conn, c.BorderWin,
		xproto.ConfigWindowSibling|xproto.ConfigWindowStackMode,
		[]uint32{uint32(c.Win), uint32(xproto.StackModeBelow)})
}
