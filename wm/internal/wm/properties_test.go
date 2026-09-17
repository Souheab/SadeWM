package wm

import (
	"testing"

	"github.com/jezek/xgb/xproto"
)

func TestProperty32Validation(t *testing.T) {
	good := xproto.GetPropertyReply{Type: xproto.AtomCardinal, Format: 32, ValueLen: 2, Value: make([]byte, 8)}
	for _, tc := range []struct {
		name string
		edit func(*xproto.GetPropertyReply)
	}{
		{"type", func(p *xproto.GetPropertyReply) { p.Type = xproto.AtomString }},
		{"format8", func(p *xproto.GetPropertyReply) { p.Format = 8 }},
		{"format16", func(p *xproto.GetPropertyReply) { p.Format = 16 }},
		{"short", func(p *xproto.GetPropertyReply) { p.Value = p.Value[:4] }},
		{"count", func(p *xproto.GetPropertyReply) { p.ValueLen = 1 }},
		{"truncated", func(p *xproto.GetPropertyReply) { p.BytesAfter = 4 }},
		{"overflow", func(p *xproto.GetPropertyReply) { p.ValueLen = ^uint32(0) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p := good
			tc.edit(&p)
			if validProperty32(&p, xproto.AtomCardinal, 2, 2) {
				t.Fatal("accepted malformed property")
			}
		})
	}
	if validProperty32(nil, xproto.AtomCardinal, 1, 1) || !validProperty32(&good, xproto.AtomCardinal, 2, 2) {
		t.Fatal("nil/valid property handling failed")
	}
}

func TestFocusEligibility(t *testing.T) {
	for _, direct := range []bool{false, true} {
		for _, protocol := range []bool{false, true} {
			for _, blockedType := range []bool{false, true} {
				c := &Client{InputNeverFocus: !direct, TakeFocus: protocol, TypeNeverFocus: blockedType}
				c.refreshFocusEligibility()
				if c.NeverFocus != (blockedType || (!direct && !protocol)) {
					t.Fatalf("wrong eligibility: %+v", c)
				}
			}
		}
	}
}
