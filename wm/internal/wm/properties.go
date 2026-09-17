package wm

import "github.com/jezek/xgb/xproto"

// validProperty32 checks the wire representation before any indexed reads.
// ValueLen counts items, not bytes; a matching type alone does not imply a
// 32-bit format. Oversized/truncated properties are treated as absent.
func validProperty32(p *xproto.GetPropertyReply, kind xproto.Atom, min, max uint32) bool {
	return p != nil && p.Type == kind && p.Format == 32 &&
		p.ValueLen >= min && p.ValueLen <= max && p.BytesAfter == 0 &&
		uint64(len(p.Value)) == uint64(p.ValueLen)*4
}

func (wm *WM) windowProperty32(win xproto.Window, prop, kind xproto.Atom, min, max uint32) []uint32 {
	p, err := xproto.GetProperty(wm.Conn, false, win, prop, kind, 0, max).Reply()
	if err != nil || !validProperty32(p, kind, min, max) {
		return nil
	}
	values := make([]uint32, p.ValueLen)
	for i := range values {
		values[i] = getUint32(p.Value[i*4:])
	}
	return values
}
