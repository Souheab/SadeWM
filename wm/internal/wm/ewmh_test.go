package wm

import (
	"testing"

	"github.com/jezek/xgb/xproto"
)

func TestAtomListAddRemovePreservesUnrelatedStates(t *testing.T) {
	fullscreen := xproto.Atom(1)
	above := xproto.Atom(2)
	sticky := xproto.Atom(3)

	states := []xproto.Atom{above, sticky}
	states = atomListAdd(states, fullscreen)
	states = atomListAdd(states, fullscreen)
	if got, want := len(states), 3; got != want {
		t.Fatalf("len after add = %d, want %d (%v)", got, want, states)
	}
	if !atomListContains(states, sticky) || !atomListContains(states, above) || !atomListContains(states, fullscreen) {
		t.Fatalf("missing expected state after add: %v", states)
	}

	states = atomListRemove(states, fullscreen)
	if atomListContains(states, fullscreen) {
		t.Fatalf("fullscreen was not removed: %v", states)
	}
	if !atomListContains(states, sticky) || !atomListContains(states, above) {
		t.Fatalf("unrelated states were not preserved: %v", states)
	}
}

func TestAtomListRemoveAboveAliases(t *testing.T) {
	fullscreen := xproto.Atom(1)
	above := xproto.Atom(2)
	staysOnTop := xproto.Atom(3)

	states := atomListRemove([]xproto.Atom{fullscreen, above, staysOnTop}, above, staysOnTop)
	if !atomListContains(states, fullscreen) {
		t.Fatalf("fullscreen was not preserved: %v", states)
	}
	if atomListContains(states, above) || atomListContains(states, staysOnTop) {
		t.Fatalf("above aliases were not removed: %v", states)
	}
}

func TestHasFloatingWindowTypeChecksAllAtoms(t *testing.T) {
	wm := &WM{}
	wm.NetAtom[NetWMWindowTypeDialog] = 20
	wm.NetAtom[NetWMWindowTypeDock] = 30

	if !wm.hasFloatingWindowType([]xproto.Atom{wm.NetAtom[NetWMWindowTypeDock], wm.NetAtom[NetWMWindowTypeDialog]}) {
		t.Fatal("expected dialog in second position to be treated as floating")
	}
	if wm.hasFloatingWindowType([]xproto.Atom{wm.NetAtom[NetWMWindowTypeDock]}) {
		t.Fatal("dock should not be treated as a floating dialog type")
	}
}
