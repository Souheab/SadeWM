package wm

import (
	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm-go/internal/config"
	"github.com/sadewm/sadewm/wm-go/internal/util"
)

// isMouseDragEvent returns true for events that should be handled inline
// during a mouse drag (ConfigureRequest / MapRequest need live processing;
// ButtonRelease / MotionNotify drive the drag itself).
func isMouseDragEvent(ev interface{}) bool {
	switch ev.(type) {
	case xproto.MotionNotifyEvent,
		xproto.ButtonPressEvent,
		xproto.ButtonReleaseEvent,
		xproto.ConfigureRequestEvent,
		xproto.MapRequestEvent:
		return true
	}
	return false
}

// nextDragEvent returns the next X event, reading from the shared event
// channel.  Events that are not drag-relevant are appended to wm.pendingEvts
// so they can be re-dispatched after the drag completes; this mirrors the
// C WM's XMaskEvent behaviour where unrelated events stay queued.
func (wm *WM) nextDragEvent() xgb.Event {
	for {
		xev := <-wm.XEvCh
		if xev.ev == nil {
			return nil
		}
		if xev.err != nil {
			wm.handleXError(xev.err)
			continue
		}
		if isMouseDragEvent(xev.ev) {
			return xev.ev
		}
		// Not drag-relevant: buffer for post-drag dispatch.
		wm.pendingEvts = append(wm.pendingEvts, xev.ev)
	}
}

// pollDragEvent does a non-blocking drain of the shared event channel.
// Drag-relevant events are returned; everything else is buffered.
// Returns nil if no drag-relevant event is immediately available.
func (wm *WM) pollDragEvent() xgb.Event {
	for {
		select {
		case xev := <-wm.XEvCh:
			if xev.ev == nil {
				return nil
			}
			if xev.err != nil {
				wm.handleXError(xev.err)
				continue
			}
			if isMouseDragEvent(xev.ev) {
				return xev.ev
			}
			wm.pendingEvts = append(wm.pendingEvts, xev.ev)
		default:
			return nil
		}
	}
}

// replayPendingEvts dispatches all events that were buffered during a drag.
func (wm *WM) replayPendingEvts() {
	for _, ev := range wm.pendingEvts {
		wm.handleEvent(ev)
	}
	wm.pendingEvts = wm.pendingEvts[:0]
}

// snapX applies horizontal snap-to-edge for a drag operation.
// It prevents the window from leaving the left/right work area edges and
// provides a magnetic snap when approaching from the outside.
func (wm *WM) snapX(nx, ocx, w int) int {
	snap := int(config.Snap)
	wx := wm.SelMon.WX
	ww := wm.SelMon.WW
	if nx < wx {
		return wx
	}
	if nx+w > wx+ww {
		return wx + ww - w
	}
	if abs(wx-nx) < snap && nx < ocx {
		return wx
	}
	if abs((wx+ww)-(nx+w)) < snap && nx > ocx {
		return wx + ww - w
	}
	return nx
}

// snapY applies vertical snap-to-edge for a drag operation.
// It prevents the window from leaving the top/bottom work area edges and
// provides a magnetic snap when approaching from the outside.
func (wm *WM) snapY(ny, ocy, h int) int {
	snap := int(config.Snap)
	wy := wm.SelMon.WY
	wh := wm.SelMon.WH
	if ny < wy {
		return wy
	}
	if ny+h > wy+wh {
		return wy + wh - h
	}
	if abs(wy-ny) < snap && ny < ocy {
		return wy
	}
	if abs((wy+wh)-(ny+h)) < snap && ny > ocy {
		return wy + wh - h
	}
	return ny
}

// MoveMouse implements Mod+Button1 window dragging.
func (wm *WM) MoveMouse(arg *config.Arg) {
	c := wm.SelMon.Sel
	if c == nil || c.IsDock || c.IsFullscreen {
		return
	}

	wm.Restack(wm.SelMon)
	ocx := c.X
	ocy := c.Y

	// Sync ensures all preceding requests from handleButtonPress (AllowEvents,
	// UngrabButton, GrabButton) have been processed by the server before we
	// attempt to grab the pointer.  Without this, GrabPointer can race against
	// those pending requests and return GrabAlreadyGrabbed or GrabFrozen.
	wm.Conn.Sync()

	reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
		xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
		xproto.GrabModeAsync, xproto.GrabModeAsync,
		xproto.WindowNone, wm.Cursors[CurMove], xproto.TimeCurrentTime).Reply()
	if err != nil || reply.Status != xproto.GrabStatusSuccess {
		util.LogDebugf("MoveMouse: GrabPointer failed (status=%d err=%v)", reply.Status, err)
		return
	}

	ptrX, ptrY := wm.getRootPtr()

	for {
		ev := wm.nextDragEvent()
		if ev == nil {
			break
		}

		switch e := ev.(type) {
		case xproto.ConfigureRequestEvent:
			wm.handleConfigureRequest(e)
		case xproto.MapRequestEvent:
			wm.handleMapRequest(e)
		case xproto.MotionNotifyEvent:
			// Coalesce: discard intermediate motion events, keep the latest.
			for {
				extra := wm.pollDragEvent()
				if extra == nil {
					break
				}
				if me, ok := extra.(xproto.MotionNotifyEvent); ok {
					e = me
				} else if _, ok := extra.(xproto.ButtonReleaseEvent); ok {
					goto done
				} else {
					// Re-buffer ConfigureRequest / MapRequest / ButtonPress
					wm.pendingEvts = append(wm.pendingEvts, extra)
				}
			}

			nx := ocx + (int(e.RootX) - ptrX)
			ny := ocy + (int(e.RootY) - ptrY)

			nx = wm.snapX(nx, ocx, c.Width())
			ny = wm.snapY(ny, ocy, c.Height())

			if !c.IsFloating && wm.SelMon.Lt.Arrange != nil {
				// Tiled mode: swap with the client under the cursor.
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
		}
	}

done:
	xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
	if m := wm.RectToMon(c.X, c.Y, c.W, c.H); m != wm.SelMon {
		wm.sendMon(c, m)
		wm.SelMon = m
		wm.Focus(nil)
	}
	wm.replayPendingEvts()
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

	wm.Conn.Sync()

	reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
		xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
		xproto.GrabModeAsync, xproto.GrabModeAsync,
		xproto.WindowNone, wm.Cursors[CurResize], xproto.TimeCurrentTime).Reply()
	if err != nil || reply.Status != xproto.GrabStatusSuccess {
		util.LogDebugf("ResizeMouse: GrabPointer failed (status=%d err=%v)", reply.Status, err)
		return
	}

	// Warp pointer to bottom-right corner of the window.
	xproto.WarpPointer(wm.Conn, xproto.WindowNone, c.Win,
		0, 0, 0, 0, int16(c.W+c.BW-1), int16(c.H+c.BW-1))

	for {
		ev := wm.nextDragEvent()
		if ev == nil {
			break
		}

		switch e := ev.(type) {
		case xproto.ConfigureRequestEvent:
			wm.handleConfigureRequest(e)
		case xproto.MapRequestEvent:
			wm.handleMapRequest(e)
		case xproto.MotionNotifyEvent:
			// Coalesce intermediate motion events.
			for {
				extra := wm.pollDragEvent()
				if extra == nil {
					break
				}
				if me, ok := extra.(xproto.MotionNotifyEvent); ok {
					e = me
				} else if _, ok := extra.(xproto.ButtonReleaseEvent); ok {
					goto done
				} else {
					wm.pendingEvts = append(wm.pendingEvts, extra)
				}
			}

			if !c.IsFloating && wm.SelMon.Lt.Arrange != nil {
				// Tiled resize adjusts mfact.
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
	wm.replayPendingEvts()
}
