package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/sadewm/sadewm/wm-go/internal/config"
	"github.com/sadewm/sadewm/wm-go/internal/util"
)

// EWMH and ICCCM property helpers

func (wm *WM) getAtomProp(c *Client, prop xproto.Atom) xproto.Atom {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win, prop,
		xproto.AtomAtom, 0, 1).Reply()
	if err != nil || reply.ValueLen == 0 {
		return xproto.AtomNone
	}
	return xproto.Atom(getUint32(reply.Value))
}

func (wm *WM) getState(w xproto.Window) int {
	reply, err := xproto.GetProperty(wm.Conn, false, w,
		wm.WMAtom[WMState], wm.WMAtom[WMState], 0, 2).Reply()
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
		wm.WMAtom[WMState], wm.WMAtom[WMState], 32, 2, data)
}

func (wm *WM) sendEvent(c *Client, proto xproto.Atom) bool {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		wm.WMAtom[WMProtocols], xproto.AtomAtom, 0, 32).Reply()
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

	if exists {
		data := xproto.ClientMessageDataUnionData32New([]uint32{
			uint32(proto),
			uint32(xproto.TimeCurrentTime),
			0, 0, 0,
		})
		ev := xproto.ClientMessageEvent{
			Format: 32,
			Window: c.Win,
			Type:   wm.WMAtom[WMProtocols],
			Data:   data,
		}
		xproto.SendEvent(wm.Conn, false, c.Win, xproto.EventMaskNoEvent, string(ev.Bytes()))
	}
	return exists
}

// updateWindowType checks EWMH window type and state atoms.
func (wm *WM) updateWindowType(c *Client) {
	state := wm.getAtomProp(c, wm.NetAtom[NetWMState])
	wtype := wm.getAtomProp(c, wm.NetAtom[NetWMWindowType])

	if state == wm.NetAtom[NetWMFullscreen] {
		wm.SetFullscreen(c, true)
	}
	if state == wm.NetAtom[NetWMStateAbove] || state == wm.NetAtom[NetWMStateStaysOnTop] {
		wm.SetAbove(c, true)
	}
	if wtype == wm.NetAtom[NetWMWindowTypeDialog] {
		c.IsFloating = true
	}
}

// updateSizeHints reads ICCCM size hints.
func (wm *WM) updateSizeHints(c *Client) {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmNormalHints, xproto.AtomWmSizeHints, 0, 18).Reply()
	if err != nil || reply.ValueLen < 18 {
		return
	}

	v := reply.Value
	flags := getUint32(v[0:])

	const (
		pMinSize    = 1 << 4
		pMaxSize    = 1 << 5
		pResizeInc  = 1 << 6
		pBaseSize   = 1 << 8
		pAspect     = 1 << 7
	)

	if flags&pBaseSize != 0 {
		c.BaseW = int(getUint32(v[40:]))
		c.BaseH = int(getUint32(v[44:]))
	} else if flags&pMinSize != 0 {
		c.BaseW = int(getUint32(v[20:]))
		c.BaseH = int(getUint32(v[24:]))
	} else {
		c.BaseW = 0
		c.BaseH = 0
	}

	if flags&pResizeInc != 0 {
		c.IncW = int(getUint32(v[28:]))
		c.IncH = int(getUint32(v[32:]))
	} else {
		c.IncW = 0
		c.IncH = 0
	}

	if flags&pMaxSize != 0 {
		c.MaxW = int(getUint32(v[36:]))
		c.MaxH = int(getUint32(v[40:]))
	} else {
		c.MaxW = 0
		c.MaxH = 0
	}

	if flags&pMinSize != 0 {
		c.MinW = int(getUint32(v[20:]))
		c.MinH = int(getUint32(v[24:]))
	} else if flags&pBaseSize != 0 {
		c.MinW = int(getUint32(v[40:]))
		c.MinH = int(getUint32(v[44:]))
	} else {
		c.MinW = 0
		c.MinH = 0
	}

	if flags&pAspect != 0 {
		minAspX := int(getUint32(v[48:]))
		minAspY := int(getUint32(v[52:]))
		maxAspX := int(getUint32(v[56:]))
		maxAspY := int(getUint32(v[60:]))
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
	c.HintsValid = true
}

// updateWMHints reads ICCCM WM_HINTS.
func (wm *WM) updateWMHints(c *Client) {
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 0, 9).Reply()
	if err != nil || reply.ValueLen == 0 {
		return
	}

	v := reply.Value
	flags := getUint32(v[0:])

	const (
		inputHint   = 1 << 0
		urgencyHint = 1 << 8
	)

	if c == wm.SelMon.Sel && flags&urgencyHint != 0 {
		// Clear urgency for focused window
		flags &^= urgencyHint
		putUint32(v[0:], flags)
		xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
			xproto.AtomWmHints, xproto.AtomWmHints, 32, reply.ValueLen, v)
	} else {
		c.IsUrgent = flags&urgencyHint != 0
	}

	if flags&inputHint != 0 {
		c.NeverFocus = getUint32(v[4:]) == 0
	} else {
		c.NeverFocus = false
	}
}

// updateTitle reads the window title.
func (wm *WM) updateTitle(c *Client) {
	name := wm.getTextProp(c.Win, wm.NetAtom[NetWMName])
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
	xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetClientList])
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			xproto.ChangeProperty(wm.Conn, xproto.PropModeAppend, wm.Root,
				wm.NetAtom[NetClientList], xproto.AtomWindow, 32, 1,
				uint32ToBytes(uint32(c.Win)))
		}
	}
}

// setUrgent sets the urgency hint on a window.
func (wm *WM) setUrgent(c *Client, urg bool) {
	c.IsUrgent = urg
	reply, err := xproto.GetProperty(wm.Conn, false, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 0, 9).Reply()
	if err != nil || reply.ValueLen == 0 {
		return
	}

	const urgencyHint = 1 << 8
	v := reply.Value
	flags := getUint32(v[0:])
	if urg {
		flags |= urgencyHint
	} else {
		flags &^= urgencyHint
	}
	putUint32(v[0:], flags)
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, c.Win,
		xproto.AtomWmHints, xproto.AtomWmHints, 32, reply.ValueLen, v)
}

func init() {
	_ = util.LogDebug
	_ = config.Tags
}
