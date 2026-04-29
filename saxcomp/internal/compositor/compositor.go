package compositor

import (
	"fmt"
	"log"

	"github.com/BurntSushi/xgb"
	"github.com/BurntSushi/xgb/composite"
	"github.com/BurntSushi/xgb/damage"
	"github.com/BurntSushi/xgb/render"
	"github.com/BurntSushi/xgb/shape"
	"github.com/BurntSushi/xgb/xfixes"
	"github.com/BurntSushi/xgb/xproto"
)

// Compositor is the main state for saxcomp.
type Compositor struct {
	conn   *xgb.Conn
	screen *xproto.ScreenInfo
	root   xproto.Window

	overlay           xproto.Window
	rootPicture       render.Picture
	xrootpmapAtom     xproto.Atom
	esetrootPmapAtom  xproto.Atom
	backgroundPixmap  xproto.Pixmap
	backgroundPicture render.Picture
	backgroundWidth   uint16
	backgroundHeight  uint16

	// Pictformats for 24-bit RGB and 32-bit ARGB windows.
	rgbFmt  render.Pictformat
	argbFmt render.Pictformat

	windows    map[xproto.Window]*Window
	stackOrder []xproto.Window

	dirty bool
	debug bool
}

// New connects to the given X display and initialises the compositor.
// Pass display="" to use the DISPLAY environment variable.
func New(display string, dbg bool) (*Compositor, error) {
	var conn *xgb.Conn
	var err error
	if display == "" {
		conn, err = xgb.NewConn()
	} else {
		conn, err = xgb.NewConnDisplay(display)
	}
	if err != nil {
		return nil, fmt.Errorf("connect to X: %w", err)
	}

	// Initialise required extensions.
	if err = composite.Init(conn); err != nil {
		conn.Close()
		return nil, fmt.Errorf("Composite extension: %w", err)
	}
	if err = render.Init(conn); err != nil {
		conn.Close()
		return nil, fmt.Errorf("Render extension: %w", err)
	}
	if err = damage.Init(conn); err != nil {
		conn.Close()
		return nil, fmt.Errorf("Damage extension: %w", err)
	}
	// QueryVersion is mandatory before any other Damage request.
	if _, err = damage.QueryVersion(conn, 1, 1).Reply(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("Damage QueryVersion: %w", err)
	}
	if err = xfixes.Init(conn); err != nil {
		conn.Close()
		return nil, fmt.Errorf("XFixes extension: %w", err)
	}
	// QueryVersion is mandatory before any other XFixes request.
	if _, err = xfixes.QueryVersion(conn, 6, 0).Reply(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("XFixes QueryVersion: %w", err)
	}
	if err = shape.Init(conn); err != nil {
		conn.Close()
		return nil, fmt.Errorf("Shape extension: %w", err)
	}

	// Verify Composite ≥ 0.4 (NameWindowPixmap requires it).
	compVer, err := composite.QueryVersion(conn, 0, 4).Reply()
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("Composite QueryVersion: %w", err)
	}
	if compVer.MajorVersion == 0 && compVer.MinorVersion < 4 {
		conn.Close()
		return nil, fmt.Errorf("Composite 0.4+ required, got %d.%d", compVer.MajorVersion, compVer.MinorVersion)
	}

	setup := xproto.Setup(conn)
	screen := setup.DefaultScreen(conn)
	root := screen.Root

	c := &Compositor{
		conn:    conn,
		screen:  screen,
		root:    root,
		windows: make(map[xproto.Window]*Window),
		debug:   dbg,
	}

	if err = c.queryPictFormats(); err != nil {
		conn.Close()
		return nil, err
	}
	if err = c.initRootBackgroundTracking(); err != nil {
		conn.Close()
		return nil, err
	}

	// Redirect all root children to offscreen pixmaps.
	if err = composite.RedirectSubwindowsChecked(conn, root, composite.RedirectAutomatic).Check(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("RedirectSubwindows: %w", err)
	}

	if err = c.setupOverlay(); err != nil {
		conn.Close()
		return nil, err
	}
	if err = c.reloadRootBackground(); err != nil {
		log.Printf("saxcomp: load root background: %v", err)
	}

	// Subscribe to root window structure events.
	const rootMask = xproto.EventMaskSubstructureNotify |
		xproto.EventMaskStructureNotify |
		xproto.EventMaskExposure |
		xproto.EventMaskPropertyChange
	if err = xproto.ChangeWindowAttributesChecked(conn, root, xproto.CwEventMask,
		[]uint32{rootMask}).Check(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("ChangeWindowAttributes: %w", err)
	}

	if err = c.scanExistingWindows(); err != nil {
		// Non-fatal: we might still compositor whatever is created later.
		log.Printf("saxcomp: scan existing windows: %v", err)
	}

	return c, nil
}

// Close releases all compositor resources and unredirects windows.
func (c *Compositor) Close() {
	for _, w := range c.windows {
		w.free(c.conn)
	}
	c.releaseRootBackground()
	if c.rootPicture != 0 {
		render.FreePicture(c.conn, c.rootPicture) //nolint:errcheck
	}
	if c.overlay != 0 {
		composite.ReleaseOverlayWindow(c.conn, c.overlay) //nolint:errcheck
	}
	composite.UnredirectSubwindows(c.conn, c.root, composite.RedirectAutomatic) //nolint:errcheck
	c.conn.Close()
}

// Run is the main event loop. It blocks until the connection is closed.
func (c *Compositor) Run() {
	if c.dirty {
		c.repaint()
	}
	for {
		ev, err := c.conn.WaitForEvent()
		if err != nil {
			if xgbErr, ok := err.(xgb.Error); ok {
				log.Printf("saxcomp: X error: %v", xgbErr)
				continue
			}
			// Connection closed.
			return
		}
		if ev == nil {
			return
		}
		c.dispatch(ev)

		if c.dirty {
			c.repaint()
		}
	}
}

// dispatch handles a single X event.
func (c *Compositor) dispatch(ev xgb.Event) {
	switch e := ev.(type) {
	case xproto.CreateNotifyEvent:
		c.onCreateNotify(e)
	case xproto.DestroyNotifyEvent:
		c.onDestroyNotify(e)
	case xproto.MapNotifyEvent:
		c.onMapNotify(e)
	case xproto.UnmapNotifyEvent:
		c.onUnmapNotify(e)
	case xproto.ConfigureNotifyEvent:
		c.onConfigureNotify(e)
	case xproto.ReparentNotifyEvent:
		c.onReparentNotify(e)
	case xproto.ExposeEvent:
		c.dirty = true
	case xproto.PropertyNotifyEvent:
		c.onPropertyNotify(e)
	case damage.NotifyEvent:
		c.onDamageNotify(e)
	}
}

// ── Event handlers ────────────────────────────────────────────────────────────

func (c *Compositor) onCreateNotify(e xproto.CreateNotifyEvent) {
	if e.Parent != c.root || e.Window == c.overlay {
		return
	}
	c.windows[e.Window] = &Window{
		id:     e.Window,
		x:      e.X,
		y:      e.Y,
		w:      e.Width,
		h:      e.Height,
		border: e.BorderWidth,
	}
	if c.debug {
		log.Printf("saxcomp: create %d (%dx%d+%d+%d)", e.Window, e.Width, e.Height, e.X, e.Y)
	}
}

func (c *Compositor) onDestroyNotify(e xproto.DestroyNotifyEvent) {
	w, ok := c.windows[e.Window]
	if !ok {
		return
	}
	w.free(c.conn)
	delete(c.windows, e.Window)
	c.dirty = true
	if c.debug {
		log.Printf("saxcomp: destroy %d", e.Window)
	}
}

func (c *Compositor) onMapNotify(e xproto.MapNotifyEvent) {
	if e.Window == c.overlay {
		return
	}
	w, ok := c.windows[e.Window]
	if !ok {
		// Window was created before we started — allocate a slot.
		geom, err := xproto.GetGeometry(c.conn, xproto.Drawable(e.Window)).Reply()
		if err != nil {
			return
		}
		w = &Window{
			id:       e.Window,
			x:        geom.X,
			y:        geom.Y,
			w:        geom.Width,
			h:        geom.Height,
			border:   geom.BorderWidth,
			hasAlpha: geom.Depth == 32,
		}
		c.windows[e.Window] = w
	}
	if err := c.mapWindow(w); err != nil {
		log.Printf("saxcomp: map window %d: %v", e.Window, err)
		return
	}
	c.dirty = true
	if c.debug {
		log.Printf("saxcomp: map %d", e.Window)
	}
}

func (c *Compositor) onUnmapNotify(e xproto.UnmapNotifyEvent) {
	w, ok := c.windows[e.Window]
	if !ok {
		return
	}
	w.free(c.conn)
	w.mapped = false
	c.dirty = true
	if c.debug {
		log.Printf("saxcomp: unmap %d", e.Window)
	}
}

func (c *Compositor) onConfigureNotify(e xproto.ConfigureNotifyEvent) {
	if e.Event != c.root {
		return
	}
	w, ok := c.windows[e.Window]
	if !ok {
		return
	}
	w.x, w.y = e.X, e.Y
	w.w, w.h = e.Width, e.Height
	w.border = e.BorderWidth
	if w.mapped {
		if err := c.mapWindow(w); err != nil {
			log.Printf("saxcomp: reconfigure window %d: %v", e.Window, err)
		}
	}
	c.dirty = true
}

func (c *Compositor) onReparentNotify(e xproto.ReparentNotifyEvent) {
	if e.Parent == c.root {
		// Window reparented into root — add it if missing.
		if _, ok := c.windows[e.Window]; !ok {
			geom, err := xproto.GetGeometry(c.conn, xproto.Drawable(e.Window)).Reply()
			if err != nil {
				return
			}
			c.windows[e.Window] = &Window{
				id:     e.Window,
				x:      geom.X,
				y:      geom.Y,
				w:      geom.Width,
				h:      geom.Height,
				border: geom.BorderWidth,
			}
		}
	} else {
		// Window reparented away from root — remove it.
		if w, ok := c.windows[e.Window]; ok {
			w.free(c.conn)
			delete(c.windows, e.Window)
			c.dirty = true
		}
	}
}

func (c *Compositor) onDamageNotify(e damage.NotifyEvent) {
	// Subtract the reported damage so future events fire again.
	if err := damage.SubtractChecked(c.conn, e.Damage, xfixes.Region(0), xfixes.Region(0)).Check(); err != nil {
		log.Printf("saxcomp: damage subtract %d: %v", e.Damage, err)
	}
	c.dirty = true
}

func (c *Compositor) onPropertyNotify(e xproto.PropertyNotifyEvent) {
	if e.Window != c.root || !c.isRootPixmapAtom(e.Atom) {
		return
	}
	if err := c.reloadRootBackground(); err != nil {
		log.Printf("saxcomp: reload root background: %v", err)
	}
	c.dirty = true
	if c.debug {
		log.Printf("saxcomp: root background property changed: atom=%d", e.Atom)
	}
}

// ── Setup helpers ─────────────────────────────────────────────────────────────

// setupOverlay creates the Composite overlay window that we draw onto.
func (c *Compositor) setupOverlay() error {
	reply, err := composite.GetOverlayWindow(c.conn, c.root).Reply()
	if err != nil {
		return fmt.Errorf("GetOverlayWindow: %w", err)
	}
	c.overlay = reply.OverlayWin

	// Clear the bounding shape to cover the full screen.
	shape.Mask(c.conn, shape.SoSet, shape.SkBounding, c.overlay, 0, 0, xproto.Pixmap(0)) //nolint:errcheck

	// Set an empty input shape so the overlay never steals pointer/keyboard events.
	shape.Rectangles(c.conn, shape.SoSet, shape.SkInput, xproto.ClipOrderingUnsorted,
		c.overlay, 0, 0, []xproto.Rectangle{}) //nolint:errcheck

	// Listen for Expose so we can repaint when needed.
	xproto.ChangeWindowAttributes(c.conn, c.overlay, xproto.CwEventMask, //nolint:errcheck
		[]uint32{xproto.EventMaskExposure})

	xproto.MapWindow(c.conn, c.overlay) //nolint:errcheck

	// Create a Picture for the overlay window.
	pid, err := render.NewPictureId(c.conn)
	if err != nil {
		return fmt.Errorf("alloc overlay picture id: %w", err)
	}
	render.CreatePicture(c.conn, pid, xproto.Drawable(c.overlay), c.rgbFmt, //nolint:errcheck
		render.CpSubwindowMode, []uint32{xproto.SubwindowModeIncludeInferiors})
	c.rootPicture = pid

	return nil
}

// queryPictFormats finds RGB24 and ARGB32 pictformats for the default screen.
func (c *Compositor) queryPictFormats() error {
	reply, err := render.QueryPictFormats(c.conn).Reply()
	if err != nil {
		return fmt.Errorf("QueryPictFormats: %w", err)
	}

	for _, f := range reply.Formats {
		if f.Type != render.PictTypeDirect {
			continue
		}
		depth := f.Depth
		d := f.Direct
		switch {
		case depth == 24 &&
			d.RedMask == 0xff && d.RedShift == 16 &&
			d.GreenMask == 0xff && d.GreenShift == 8 &&
			d.BlueMask == 0xff && d.BlueShift == 0:
			c.rgbFmt = f.Id
		case depth == 32 &&
			d.AlphaMask == 0xff && d.AlphaShift == 24 &&
			d.RedMask == 0xff && d.RedShift == 16 &&
			d.GreenMask == 0xff && d.GreenShift == 8 &&
			d.BlueMask == 0xff && d.BlueShift == 0:
			c.argbFmt = f.Id
		}
	}

	if c.rgbFmt == 0 {
		return fmt.Errorf("no RGB24 pictformat found")
	}
	return nil
}

// scanExistingWindows adds all currently-mapped direct children of root.
func (c *Compositor) scanExistingWindows() error {
	tree, err := xproto.QueryTree(c.conn, c.root).Reply()
	if err != nil {
		return fmt.Errorf("QueryTree: %w", err)
	}
	for _, child := range tree.Children {
		if child == c.overlay {
			continue
		}
		attrs, err := xproto.GetWindowAttributes(c.conn, child).Reply()
		if err != nil {
			continue
		}
		geom, err := xproto.GetGeometry(c.conn, xproto.Drawable(child)).Reply()
		if err != nil {
			continue
		}
		w := &Window{
			id:       child,
			x:        geom.X,
			y:        geom.Y,
			w:        geom.Width,
			h:        geom.Height,
			border:   geom.BorderWidth,
			hasAlpha: geom.Depth == 32,
		}
		c.windows[child] = w
		if attrs.MapState == xproto.MapStateViewable {
			if err := c.mapWindow(w); err != nil {
				log.Printf("saxcomp: scan map window %d: %v", child, err)
			}
		}
	}
	c.dirty = true
	return nil
}

// mapWindow binds a Pixmap + Picture + Damage to a window that just became mapped.
func (c *Compositor) mapWindow(w *Window) error {
	resources, err := c.newWindowResources(w.id)
	if err != nil {
		return err
	}
	w.replaceResources(c.conn, resources)
	w.mapped = true
	return nil
}

func (c *Compositor) newWindowResources(id xproto.Window) (windowResources, error) {
	resources := windowResources{}

	// NameWindowPixmap gives us the redirected offscreen pixmap.
	pid, err := xproto.NewPixmapId(c.conn)
	if err != nil {
		return resources, fmt.Errorf("alloc pixmap id: %w", err)
	}
	resources.pixmap = pid
	if err := composite.NameWindowPixmapChecked(c.conn, id, pid).Check(); err != nil {
		resources.release(c.conn)
		return resources, fmt.Errorf("NameWindowPixmap: %w", err)
	}

	// Choose the right pictformat based on window depth.
	wGeom, err := xproto.GetGeometry(c.conn, xproto.Drawable(id)).Reply()
	if err != nil {
		resources.release(c.conn)
		return resources, fmt.Errorf("GetGeometry for depth: %w", err)
	}
	resources.hasAlpha = wGeom.Depth == 32
	picFmt := c.rgbFmt
	if resources.hasAlpha && c.argbFmt != 0 {
		picFmt = c.argbFmt
	}

	// Create a Picture for the pixmap.
	pictID, err := render.NewPictureId(c.conn)
	if err != nil {
		resources.release(c.conn)
		return resources, fmt.Errorf("alloc picture id: %w", err)
	}
	resources.picture = pictID
	if err := render.CreatePictureChecked(c.conn, pictID, xproto.Drawable(resources.pixmap), picFmt,
		render.CpSubwindowMode, []uint32{xproto.SubwindowModeIncludeInferiors}).Check(); err != nil {
		resources.release(c.conn)
		return resources, fmt.Errorf("CreatePicture: %w", err)
	}

	// Register a Damage object so we get notified when this window is drawn to.
	dmgID, err := damage.NewDamageId(c.conn)
	if err != nil {
		resources.release(c.conn)
		return resources, fmt.Errorf("alloc damage id: %w", err)
	}
	resources.dmg = dmgID
	if err := damage.CreateChecked(c.conn, dmgID, xproto.Drawable(id),
		damage.ReportLevelNonEmpty).Check(); err != nil {
		// Non-fatal: window still renders; we just won't get damage events for it.
		log.Printf("saxcomp: damage.Create for %d: %v (no damage tracking)", id, err)
		resources.dmg = 0
	}

	return resources, nil
}

// updateStackOrder refreshes stackOrder from the server's current window tree.
func (c *Compositor) updateStackOrder() {
	tree, err := xproto.QueryTree(c.conn, c.root).Reply()
	if err != nil {
		return
	}
	c.stackOrder = c.stackOrder[:0]
	for _, child := range tree.Children {
		if child != c.overlay {
			c.stackOrder = append(c.stackOrder, child)
		}
	}
}
