package wm

import (
	"github.com/BurntSushi/xgb/xproto"
	"github.com/BurntSushi/xgbutil/keybind"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// GrabKeys grabs all active key bindings on the root window.
func (wm *WM) GrabKeys() {
	keybind.Initialize(wm.X)

	wm.updateNumlockMask()

	xproto.UngrabKey(wm.Conn, xproto.GrabAny, wm.Root, xproto.ModMaskAny)

	modifiers := []uint16{0, xproto.ModMaskLock, wm.NumlockMask, wm.NumlockMask | xproto.ModMaskLock}

	for _, key := range wm.ActiveKeys {
		codes := keybind.StrToKeycodes(wm.X, key.KeyStr)
		for _, code := range codes {
			for _, mod := range modifiers {
				xproto.GrabKey(wm.Conn, true, wm.Root,
					key.Mod|mod, xproto.Keycode(code),
					xproto.GrabModeAsync, xproto.GrabModeAsync)
			}
		}
	}
}

// GrabButtons grabs mouse buttons on a client window.
func (wm *WM) GrabButtons(c *Client, focused bool) {
	wm.updateNumlockMask()
	modifiers := []uint16{0, xproto.ModMaskLock, wm.NumlockMask, wm.NumlockMask | xproto.ModMaskLock}

	xproto.UngrabButton(wm.Conn, xproto.ButtonIndexAny, c.Win, xproto.ModMaskAny)

	if !focused {
		xproto.GrabButton(wm.Conn, false, c.Win,
			xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease,
			xproto.GrabModeSync, xproto.GrabModeSync,
			xproto.WindowNone, xproto.CursorNone, xproto.ButtonIndexAny, xproto.ModMaskAny)
	}

	buttons := config.DefaultButtons()
	for _, btn := range buttons {
		if btn.Click == config.ClkClientWin {
			for _, mod := range modifiers {
				xproto.GrabButton(wm.Conn, false, c.Win,
					xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease,
					xproto.GrabModeAsync, xproto.GrabModeSync,
					xproto.WindowNone, xproto.CursorNone,
					byte(btn.Button), btn.Mask|mod)
			}
		}
	}
}

func (wm *WM) updateNumlockMask() {
	wm.NumlockMask = 0
	reply, err := xproto.GetModifierMapping(wm.Conn).Reply()
	if err != nil {
		return
	}

	// Find Num_Lock keysym → keycode
	numLockCode := keybind.StrToKeycodes(wm.X, "Num_Lock")
	if len(numLockCode) == 0 {
		return
	}

	kpm := int(reply.KeycodesPerModifier)
	for i := 0; i < 8; i++ {
		for j := 0; j < kpm; j++ {
			kc := reply.Keycodes[i*kpm+j]
			for _, nlc := range numLockCode {
				if kc == xproto.Keycode(nlc) {
					wm.NumlockMask = 1 << uint(i)
				}
			}
		}
	}
}

// cleanMask strips numlock and capslock from a modifier mask.
func (wm *WM) cleanMask(mask uint16) uint16 {
	return mask &^ (wm.NumlockMask | xproto.ModMaskLock) &
		(xproto.ModMaskShift | xproto.ModMaskControl |
			xproto.ModMask1 | xproto.ModMask2 | xproto.ModMask3 | xproto.ModMask4 | xproto.ModMask5)
}

func init() {
	_ = util.LogDebug // unused import guard
}
