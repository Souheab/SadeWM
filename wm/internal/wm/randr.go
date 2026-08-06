package wm

import (
	"fmt"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
)

// randrNotifyEvent is intentionally small: sadewm only needs a wake-up when
// topology changes, then obtains authoritative monitor rectangles through
// Xinerama. Keeping this wire shim local avoids carrying a second generated
// X11 protocol package solely for QueryVersion and SelectInput.
type randrNotifyEvent struct {
	raw [32]byte
}

func newRandRNotifyEvent(buf []byte) xgb.Event {
	e := randrNotifyEvent{}
	copy(e.raw[:], buf)
	return e
}

func (e randrNotifyEvent) Bytes() []byte { return e.raw[:] }
func (e randrNotifyEvent) String() string {
	return fmt.Sprintf("RandRNotify{type=%d subtype=%d}", e.raw[0]&127, e.raw[1])
}

func (wm *WM) initRandR() {
	reply, err := xproto.QueryExtension(wm.Conn, uint16(len("RANDR")), "RANDR").Reply()
	if err != nil || reply == nil || !reply.Present {
		wm.RandRAvailable = false
		return
	}
	wm.RandRAvailable = true
	wm.RandROpcode = reply.MajorOpcode
	wm.RandREventBase = reply.FirstEvent
	xgb.NewEventFuncs[int(reply.FirstEvent)] = newRandRNotifyEvent
	xgb.NewEventFuncs[int(reply.FirstEvent)+1] = newRandRNotifyEvent

	// QueryVersion 1.6. Older servers negotiate down in their reply.
	version := make([]byte, 12)
	version[0] = reply.MajorOpcode
	version[1] = 0
	xgb.Put16(version[2:], 3)
	xgb.Put32(version[4:], 1)
	xgb.Put32(version[8:], 6)
	cookie := wm.Conn.NewCookie(true, true)
	wm.Conn.NewRequest(version, cookie)
	if _, err := cookie.Reply(); err != nil {
		wm.RandRAvailable = false
		return
	}

	// SelectInput: screen, CRTC, output, output-property, provider, and
	// resource-change notifications. Unknown high mask bits are ignored by
	// servers that negotiated an older protocol version.
	request := make([]byte, 12)
	request[0] = reply.MajorOpcode
	request[1] = 4
	xgb.Put16(request[2:], 3)
	xgb.Put32(request[4:], uint32(wm.Root))
	xgb.Put16(request[8:], 0x00ff)
	wm.Conn.NewRequest(request, wm.Conn.NewCookie(false, false))
}
