package compositor

import (
	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/damage"
	"github.com/BurntSushi/xgb/render"
	"github.com/BurntSushi/xgb/xproto"
)

type windowResources struct {
	pixmap   xproto.Pixmap
	picture  render.Picture
	dmg      damage.Damage
	hasAlpha bool
}

func (res *windowResources) release(conn *xgb.Conn) {
	if res.picture != 0 {
		render.FreePictureChecked(conn, res.picture).Check() //nolint:errcheck
		res.picture = 0
	}
	if res.pixmap != 0 {
		xproto.FreePixmapChecked(conn, res.pixmap).Check() //nolint:errcheck
		res.pixmap = 0
	}
	if res.dmg != 0 {
		damage.DestroyChecked(conn, res.dmg).Check() //nolint:errcheck
		res.dmg = 0
	}
	res.hasAlpha = false
}

// Window holds the compositor state for a single X window.
type Window struct {
	id       xproto.Window
	x, y     int16
	w, h     uint16
	border   uint16
	mapped   bool
	pixmap   xproto.Pixmap
	picture  render.Picture
	dmg      damage.Damage
	hasAlpha bool
}

func (w *Window) replaceResources(conn *xgb.Conn, resources windowResources) {
	old := windowResources{
		pixmap:  w.pixmap,
		picture: w.picture,
		dmg:     w.dmg,
	}

	w.pixmap = resources.pixmap
	w.picture = resources.picture
	w.dmg = resources.dmg
	w.hasAlpha = resources.hasAlpha

	old.release(conn)
}

// free releases all X resources associated with this window.
func (w *Window) free(conn *xgb.Conn) {
	w.replaceResources(conn, windowResources{})
}
