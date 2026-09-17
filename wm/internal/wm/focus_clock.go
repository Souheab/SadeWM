package wm

import (
	"time"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/util"
)

const focusClockTimeout = time.Second

// A private connection keeps timestamp queries out of the WM's event stream.
// It owns only an unmapped window and is reused until failure or shutdown.
type focusClock struct {
	conn *xgb.Conn
	win  xproto.Window
}

func newFocusClock() *focusClock {
	ready := make(chan *xgb.Conn)
	cancel := make(chan struct{})
	defer close(cancel)
	go func() {
		conn, _ := xgb.NewConn()
		select {
		case ready <- conn:
		case <-cancel:
			if conn != nil {
				conn.Close()
			}
		}
	}()
	select {
	case conn := <-ready:
		if conn != nil {
			return &focusClock{conn: conn}
		}
	case <-time.After(focusClockTimeout):
	}
	return nil
}

func (clock *focusClock) timestamp() uint32 {
	result := make(chan uint32, 1)
	go func() {
		if clock.win == 0 {
			win, err := xproto.NewWindowId(clock.conn)
			if err != nil {
				result <- 0
				return
			}
			clock.win = win
			root := xproto.Setup(clock.conn).Roots[clock.conn.DefaultScreen].Root
			xproto.CreateWindow(clock.conn, 0, win, root, 0, 0, 1, 1, 0,
				xproto.WindowClassInputOnly, 0, xproto.CwEventMask,
				[]uint32{xproto.EventMaskPropertyChange})
		}
		xproto.ChangeProperty(clock.conn, xproto.PropModeReplace, clock.win,
			xproto.AtomWmName, xproto.AtomString, 8, 0, nil)
		for {
			event, err := clock.conn.WaitForEvent()
			if err != nil || event == nil {
				result <- 0
				return
			}
			if e, ok := event.(xproto.PropertyNotifyEvent); ok && e.Window == clock.win {
				result <- uint32(e.Time)
				return
			}
		}
	}()
	select {
	case timestamp := <-result:
		return timestamp
	case <-time.After(focusClockTimeout):
		clock.conn.Close()
		return 0
	}
}

func (wm *WM) focusTimestamp() uint32 {
	if wm.focusEventTime != 0 {
		return wm.focusEventTime
	}
	// Complete preceding focus changes on our main connection before sampling
	// time on the helper connection (notably restore followed by activation).
	wm.Conn.Sync()
	if wm.focusClock == nil {
		wm.focusClock = newFocusClock()
	}
	if wm.focusClock != nil {
		if timestamp := wm.focusClock.timestamp(); timestamp != 0 {
			return timestamp
		}
		wm.focusClock.conn.Close()
		wm.focusClock = nil
	}
	util.LogInfo("could not obtain X timestamp for focus; skipping WM_TAKE_FOCUS")
	return 0
}
