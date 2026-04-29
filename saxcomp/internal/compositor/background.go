package compositor

import (
	"fmt"
	"log"

	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/render"
	"github.com/BurntSushi/xgb/xproto"
)

func (c *Compositor) initRootBackgroundTracking() error {
	xrootpmapAtom, err := c.internAtom("_XROOTPMAP_ID")
	if err != nil {
		return err
	}
	esetrootPmapAtom, err := c.internAtom("ESETROOT_PMAP_ID")
	if err != nil {
		return err
	}

	c.xrootpmapAtom = xrootpmapAtom
	c.esetrootPmapAtom = esetrootPmapAtom
	return nil
}

func (c *Compositor) internAtom(name string) (xproto.Atom, error) {
	reply, err := xproto.InternAtom(c.conn, false, uint16(len(name)), name).Reply()
	if err != nil {
		return 0, fmt.Errorf("intern atom %s: %w", name, err)
	}
	if reply == nil {
		return 0, fmt.Errorf("intern atom %s: empty reply", name)
	}
	return reply.Atom, nil
}

func (c *Compositor) reloadRootBackground() error {
	c.releaseRootBackground()

	pixmap, err := c.rootBackgroundPixmap()
	if err != nil {
		return err
	}
	if pixmap == 0 {
		return nil
	}

	geom, err := xproto.GetGeometry(c.conn, xproto.Drawable(pixmap)).Reply()
	if err != nil {
		return fmt.Errorf("get root background geometry: %w", err)
	}

	picFmt, err := c.pictureFormatForDepth(geom.Depth)
	if err != nil {
		return err
	}

	pictureID, err := render.NewPictureId(c.conn)
	if err != nil {
		return fmt.Errorf("alloc root background picture id: %w", err)
	}
	if err := render.CreatePictureChecked(c.conn, pictureID, xproto.Drawable(pixmap), picFmt, 0, nil).Check(); err != nil {
		return fmt.Errorf("bind root background picture: %w", err)
	}

	c.backgroundPixmap = pixmap
	c.backgroundPicture = pictureID
	c.backgroundWidth = geom.Width
	c.backgroundHeight = geom.Height
	return nil
}

func (c *Compositor) rootBackgroundPixmap() (xproto.Pixmap, error) {
	for _, atom := range []xproto.Atom{c.xrootpmapAtom, c.esetrootPmapAtom} {
		if atom == 0 {
			continue
		}

		reply, err := xproto.GetProperty(c.conn, false, c.root, atom, xproto.AtomPixmap, 0, 1).Reply()
		if err != nil {
			return 0, fmt.Errorf("get root background property %d: %w", atom, err)
		}
		if reply == nil || reply.Type != xproto.AtomPixmap || reply.Format != 32 || reply.ValueLen < 1 {
			continue
		}

		pixmap := xproto.Pixmap(xgb.Get32(reply.Value))
		if pixmap != 0 {
			return pixmap, nil
		}
	}

	return 0, nil
}

func (c *Compositor) releaseRootBackground() {
	if c.backgroundPicture != 0 {
		if err := render.FreePictureChecked(c.conn, c.backgroundPicture).Check(); err != nil {
			log.Printf("saxcomp: free root background picture: %v", err)
		}
		c.backgroundPicture = 0
	}

	c.backgroundPixmap = 0
	c.backgroundWidth = 0
	c.backgroundHeight = 0
}

func (c *Compositor) pictureFormatForDepth(depth byte) (render.Pictformat, error) {
	switch depth {
	case 24:
		if c.rgbFmt != 0 {
			return c.rgbFmt, nil
		}
	case 32:
		if c.argbFmt != 0 {
			return c.argbFmt, nil
		}
	}

	return 0, fmt.Errorf("no render pictformat for depth %d", depth)
}

func (c *Compositor) isRootPixmapAtom(atom xproto.Atom) bool {
	return atom != 0 && (atom == c.xrootpmapAtom || atom == c.esetrootPmapAtom)
}
