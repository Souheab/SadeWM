package wm

import (
	"github.com/jezek/xgb/xproto"
	"github.com/sadewm/sadewm/wm/internal/config"
	"testing"
)

func TestClientLookupUsesWindowAndFrameIndexes(t *testing.T) {
	client := &Client{Win: 10, FrameWin: 20}
	wm := &WM{ClientMap: map[xproto.Window]*Client{10: client}, FrameMap: map[xproto.Window]*Client{20: client}}
	if wm.winToClient(10) != client || wm.winToClient(20) != client || wm.winToClient(30) != nil {
		t.Fatal("client/frame lookup did not use the indexes")
	}
}

func TestUnchangedStateDoesNotNeedXConnection(t *testing.T) {
	client := &Client{statePublished: true, publishedState: []xproto.Atom{1, 2}}
	wm := &WM{}
	wm.setNetWMState(client, []xproto.Atom{1, 2})
}

func TestSizeHintWhitelistUsesCachedClass(t *testing.T) {
	original := config.SizeHintsWhitelist
	defer func() { config.SizeHintsWhitelist = original }()
	config.SizeHintsWhitelist = []string{"Editor"}
	wm := &WM{}
	if !wm.honorSizeHints(&Client{Class: "Editor"}) || !wm.honorSizeHints(&Client{Instance: "Editor"}) {
		t.Fatal("cached class/instance did not match whitelist")
	}
	if wm.honorSizeHints(&Client{Class: "Other"}) {
		t.Fatal("unlisted class matched")
	}
}
