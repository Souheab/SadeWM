package compositor

import (
	"log"

	"github.com/jezek/xgb/render"
	"github.com/jezek/xgb/xproto"
)

// repaint composites all mapped windows onto the overlay in stack order.
func (c *Compositor) repaint() {
	c.updateStackOrder()
	hadErrors := false

	// Fill the overlay with solid black as the background.
	black := render.Color{Red: 0, Green: 0, Blue: 0, Alpha: 0xffff}
	fullScreen := xproto.Rectangle{
		X: 0, Y: 0,
		Width:  c.screen.WidthInPixels,
		Height: c.screen.HeightInPixels,
	}
	if err := render.FillRectanglesChecked(c.conn, render.PictOpSrc, c.rootPicture, black,
		[]xproto.Rectangle{fullScreen}).Check(); err != nil {
		log.Printf("saxcomp: fill background: %v", err)
		return
	}
	if c.backgroundPicture != 0 && c.backgroundWidth != 0 && c.backgroundHeight != 0 {
		bgWidth := c.backgroundWidth
		bgHeight := c.backgroundHeight
		if bgWidth > c.screen.WidthInPixels {
			bgWidth = c.screen.WidthInPixels
		}
		if bgHeight > c.screen.HeightInPixels {
			bgHeight = c.screen.HeightInPixels
		}
		if err := render.CompositeChecked(c.conn, byte(render.PictOpSrc), c.backgroundPicture, render.Picture(0),
			c.rootPicture,
			0, 0, // src x, y
			0, 0, // mask x, y
			0, 0, // dst x, y
			bgWidth, bgHeight, // width, height
		).Check(); err != nil {
			hadErrors = true
			log.Printf("saxcomp: composite root background: %v", err)
		}
	}

	// Composite windows bottom-to-top.
	for _, id := range c.stackOrder {
		w, ok := c.windows[id]
		if !ok || !w.mapped || w.picture == 0 {
			continue
		}
		op := render.PictOpSrc
		if w.hasAlpha {
			op = render.PictOpOver
		}
		// x/y include the border offset.
		dstX := int16(w.x - int16(w.border))
		dstY := int16(w.y - int16(w.border))
		totalW := w.w + 2*w.border
		totalH := w.h + 2*w.border
		if err := render.CompositeChecked(c.conn, byte(op), w.picture, render.Picture(0),
			c.rootPicture,
			0, 0, // src x, y
			0, 0, // mask x, y
			dstX, dstY, // dst x, y
			totalW, totalH, // width, height
		).Check(); err != nil {
			hadErrors = true
			log.Printf("saxcomp: composite window %d: %v", id, err)
		}
	}

	c.conn.Sync()
	c.dirty = hadErrors
}
