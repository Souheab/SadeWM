package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm-go/internal/config"
	"github.com/sadewm/sadewm/wm-go/internal/util"
)

// movemouse implements Mod+Button1 window dragging.
func (wm *WM) MoveMouse(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil || c.IsDock || c.IsFullscreen {
		return
	}

	wm.Restack(wm.SelMon)
	ocx := c.X
	ocy := c.Y

	reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
		xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
		xproto.GrabModeAsync, xproto.GrabModeAsync,
		xproto.WindowNone, wm.Cursors[CurMove], xproto.TimeCurrentTime).Reply()
	if err != nil || reply.Status != xproto.GrabStatusSuccess {
		return
	}

	ptrX, ptrY := wm.getRootPtr()

	for {
		ev, _ := wm.Conn.WaitForEvent()
		if ev == nil {
			break
		}

		switch e := ev.(type) {
		case xproto.MotionNotifyEvent:
			// Drain excess motion events
			for {
				extra, _ := wm.Conn.PollForEvent()
				if extra == nil {
					break
				}
				if me, ok := extra.(xproto.MotionNotifyEvent); ok {
					e = me
				} else {
					wm.handleEvent(extra)
					break
				}
			}

			nx := ocx + (int(e.RootX) - ptrX)
			ny := ocy + (int(e.RootY) - ptrY)

			snap := int(config.Snap)
			if abs(wm.SelMon.WX-nx) < snap {
				nx = wm.SelMon.WX
			} else if abs((wm.SelMon.WX+wm.SelMon.WW)-(nx+c.Width())) < snap {
				nx = wm.SelMon.WX + wm.SelMon.WW - c.Width()
			}
			if abs(wm.SelMon.WY-ny) < snap {
				ny = wm.SelMon.WY
			} else if abs((wm.SelMon.WY+wm.SelMon.WH)-(ny+c.Height())) < snap {
				ny = wm.SelMon.WY + wm.SelMon.WH - c.Height()
			}

			if !c.IsFloating && wm.SelMon.Lt.Arrange != nil {
				// Swap with client under cursor
				m := wm.winToMon(c.Win)
				for t := m.Clients; t != nil; t = t.Next {
					if t != c && !t.IsFloating && t.IsVisible() &&
						int(e.RootX) >= t.X && int(e.RootX) <= t.X+t.W &&
						int(e.RootY) >= t.Y && int(e.RootY) <= t.Y+t.H {
						wm.SwapClients(c, t)
						break
					}
				}
			} else {
				wm.Resize(c, nx, ny, c.W, c.H, true)
			}

		case xproto.ButtonReleaseEvent:
			goto done

		default:
			wm.handleEvent(ev)
		}
	}

done:
	xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
	if m := wm.RectToMon(c.X, c.Y, c.W, c.H); m != wm.SelMon {
		wm.sendMon(c, m)
		wm.SelMon = m
		wm.Focus(nil)
	}
}

// ResizeMouse implements Mod+Button3 window resizing.
func (wm *WM) ResizeMouse(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil || c.IsDock || c.IsFullscreen {
		return
	}

	wm.Restack(wm.SelMon)
	ocx := c.X
	ocy := c.Y

	reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
		xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
		xproto.GrabModeAsync, xproto.GrabModeAsync,
		xproto.WindowNone, wm.Cursors[CurResize], xproto.TimeCurrentTime).Reply()
	if err != nil || reply.Status != xproto.GrabStatusSuccess {
		return
	}

	// Warp pointer to bottom-right corner
	xproto.WarpPointer(wm.Conn, xproto.WindowNone, c.Win,
		0, 0, 0, 0, int16(c.W+c.BW-1), int16(c.H+c.BW-1))

	for {
		ev, _ := wm.Conn.WaitForEvent()
		if ev == nil {
			break
		}

		switch e := ev.(type) {
		case xproto.MotionNotifyEvent:
			for {
				extra, _ := wm.Conn.PollForEvent()
				if extra == nil {
					break
				}
				if me, ok := extra.(xproto.MotionNotifyEvent); ok {
					e = me
				} else {
					wm.handleEvent(extra)
					break
				}
			}

			if !c.IsFloating && wm.SelMon.Lt.Arrange != nil {
				// Adjust mfact for tiled resize
				f := float32(int(e.RootX)-wm.SelMon.WX) / float32(wm.SelMon.WW)
				if wm.SelMon.IsRightTiled {
					f = 1.0 - f
				}
				wm.SetMFact(&config.Arg{F: f + 1.0})
				continue
			}

			nw := max(int(e.RootX)-ocx-2*c.BW+1, 1)
			nh := max(int(e.RootY)-ocy-2*c.BW+1, 1)

			if c.Mon.WX+nw >= wm.SelMon.WX && c.Mon.WX+nw <= wm.SelMon.WX+wm.SelMon.WW &&
				c.Mon.WY+nh >= wm.SelMon.WY && c.Mon.WY+nh <= wm.SelMon.WY+wm.SelMon.WH {
				snap := int(config.Snap)
				if !c.IsFloating && wm.SelMon.Lt.Arrange != nil &&
					(abs(nw-c.W) > snap || abs(nh-c.H) > snap) {
					wm.ToggleFloating(nil)
				}
			}
			if wm.SelMon.Lt.Arrange == nil || c.IsFloating {
				wm.Resize(c, c.X, c.Y, nw, nh, true)
			}

		case xproto.ButtonReleaseEvent:
			goto done

		default:
			wm.handleEvent(ev)
		}
	}

done:
	xproto.WarpPointer(wm.Conn, xproto.WindowNone, c.Win,
		0, 0, 0, 0, int16(c.W+c.BW-1), int16(c.H+c.BW-1))
	xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)

	if m := wm.RectToMon(c.X, c.Y, c.W, c.H); m != wm.SelMon {
		wm.sendMon(c, m)
		wm.SelMon = m
		wm.Focus(nil)
	}
}

func init() {
	_ = util.LogDebug // unused import guard
}
