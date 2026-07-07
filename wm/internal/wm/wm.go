package wm

import (
	"fmt"
	"image"
	_ "image/jpeg"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/shape"
	"github.com/jezek/xgb/xproto"
	"github.com/jezek/xgbutil"

	"github.com/sadewm/sadewm/wm/internal/config"
	"github.com/sadewm/sadewm/wm/internal/ipc"
	"github.com/sadewm/sadewm/wm/internal/util"
)

// New creates a new WM instance but does not connect to X yet.
func New() *WM {
	wm := &WM{
		ActiveRules:   config.DefaultRules,
		ActiveKeys:    config.DefaultKeys(),
		Layouts:       make([]config.Layout, len(config.DefaultLayouts)),
		MinimizeStack: make([]*Client, 0),
		Actions:       make(map[string]config.ActionFunc),
		TitlebarMap:   make(map[xproto.Window]*Client),
		FrameMap:      make(map[xproto.Window]*Client),
		QuitCh:        make(chan struct{}),
	}
	wm.Running.Store(true)
	copy(wm.Layouts, config.DefaultLayouts)
	// Set tile arrange function
	wm.Layouts[config.LayoutTile].Arrange = func(m any) {
		wm.Tile(m.(*Monitor))
	}
	return wm
}

// Setup connects to X11, sets up atoms, cursors, EWMH, and selects events.
func (wm *WM) Setup() {
	var err error

	wm.X, err = xgbutil.NewConn()
	if err != nil {
		util.Die("sadewm: cannot open display: %v", err)
	}
	wm.Conn = wm.X.Conn()
	if err := shape.Init(wm.Conn); err == nil {
		wm.ShapeAvailable = true
	}

	// Check for another WM
	wm.checkOtherWM()

	setup := xproto.Setup(wm.Conn)
	wm.Screen = &setup.Roots[wm.X.Conn().DefaultScreen]
	wm.Root = wm.Screen.Root
	wm.SW = int(wm.Screen.WidthInPixels)
	wm.SH = int(wm.Screen.HeightInPixels)

	wm.updateGeom()
	wm.internAtoms()
	wm.createCursors()
	wm.allocColors()

	// Create wmcheckwin
	wm.WMCheckWin, _ = xproto.NewWindowId(wm.Conn)
	xproto.CreateWindow(wm.Conn, wm.Screen.RootDepth, wm.WMCheckWin, wm.Root,
		0, 0, 1, 1, 0, xproto.WindowClassInputOutput, wm.Screen.RootVisual, 0, nil)

	// Set _NET_SUPPORTING_WM_CHECK on both root and check window
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.WMCheckWin,
		wm.NetAtom[NetWMCheck], xproto.AtomWindow, 32, 1, uint32ToBytes(uint32(wm.WMCheckWin)))
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.WMCheckWin,
		wm.NetAtom[NetWMName], wm.UTF8, 8, uint32(len("sadewm")), []byte("sadewm"))
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.NetAtom[NetWMCheck], xproto.AtomWindow, 32, 1, uint32ToBytes(uint32(wm.WMCheckWin)))

	// Set _NET_SUPPORTED
	atomData := make([]byte, 4*NetLast)
	for i := 0; i < NetLast; i++ {
		putUint32(atomData[i*4:], uint32(wm.NetAtom[i]))
	}
	xproto.ChangeProperty(wm.Conn, xproto.PropModeReplace, wm.Root,
		wm.NetAtom[NetSupported], xproto.AtomAtom, 32, uint32(NetLast), atomData)

	// Delete _NET_CLIENT_LIST
	xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetClientList])

	// Select events on root
	xproto.ChangeWindowAttributes(wm.Conn, wm.Root, xproto.CwEventMask|xproto.CwCursor,
		[]uint32{
			xproto.EventMaskSubstructureRedirect |
				xproto.EventMaskSubstructureNotify |
				xproto.EventMaskButtonPress |
				xproto.EventMaskPointerMotion |
				xproto.EventMaskEnterWindow |
				xproto.EventMaskLeaveWindow |
				xproto.EventMaskStructureNotify |
				xproto.EventMaskPropertyChange,
			uint32(wm.Cursors[CurNormal]),
		})

	wm.GrabKeys()
	wm.Focus(nil)

	wm.RegisterActions()
	wm.initXlibDpy()
}

func (wm *WM) checkOtherWM() {
	// Try to select SubstructureRedirect on the root window.
	// If another WM is running, this will fail.
	err := xproto.ChangeWindowAttributesChecked(wm.Conn,
		xproto.Setup(wm.Conn).Roots[wm.Conn.DefaultScreen].Root,
		xproto.CwEventMask,
		[]uint32{xproto.EventMaskSubstructureRedirect}).Check()
	if err != nil {
		util.Die("sadewm: another window manager is already running")
	}
}

func (wm *WM) internAtoms() {
	atomNames := map[int]string{
		NetSupported:                "_NET_SUPPORTED",
		NetWMName:                   "_NET_WM_NAME",
		NetWMState:                  "_NET_WM_STATE",
		NetWMCheck:                  "_NET_SUPPORTING_WM_CHECK",
		NetWMFullscreen:             "_NET_WM_STATE_FULLSCREEN",
		NetActiveWindow:             "_NET_ACTIVE_WINDOW",
		NetWMWindowType:             "_NET_WM_WINDOW_TYPE",
		NetWMStateAbove:             "_NET_WM_STATE_ABOVE",
		NetWMStateStaysOnTop:        "_NET_WM_STATE_STAYS_ON_TOP",
		NetWMWindowTypeDialog:       "_NET_WM_WINDOW_TYPE_DIALOG",
		NetWMWindowTypeDock:         "_NET_WM_WINDOW_TYPE_DOCK",
		NetClientList:               "_NET_CLIENT_LIST",
		NetWMWindowTypeUtility:      "_NET_WM_WINDOW_TYPE_UTILITY",
		NetWMWindowTypeSplash:       "_NET_WM_WINDOW_TYPE_SPLASH",
		NetWMWindowTypeToolbar:      "_NET_WM_WINDOW_TYPE_TOOLBAR",
		NetWMWindowTypePopupMenu:    "_NET_WM_WINDOW_TYPE_POPUP_MENU",
		NetWMWindowTypeDropdownMenu: "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
		NetWMWindowTypeTooltip:      "_NET_WM_WINDOW_TYPE_TOOLTIP",
		NetWMWindowTypeNotification: "_NET_WM_WINDOW_TYPE_NOTIFICATION",
		NetFrameExtents:             "_NET_FRAME_EXTENTS",
	}
	for idx, name := range atomNames {
		reply, err := xproto.InternAtom(wm.Conn, false, uint16(len(name)), name).Reply()
		if err == nil {
			wm.NetAtom[idx] = reply.Atom
		}
	}

	wmAtomNames := map[int]string{
		WMProtocols: "WM_PROTOCOLS",
		WMDelete:    "WM_DELETE_WINDOW",
		WMState:     "WM_STATE",
		WMTakeFocus: "WM_TAKE_FOCUS",
	}
	for idx, name := range wmAtomNames {
		reply, err := xproto.InternAtom(wm.Conn, false, uint16(len(name)), name).Reply()
		if err == nil {
			wm.WMAtom[idx] = reply.Atom
		}
	}

	reply, err := xproto.InternAtom(wm.Conn, false, uint16(len("UTF8_STRING")), "UTF8_STRING").Reply()
	if err == nil {
		wm.UTF8 = reply.Atom
	}
}

func (wm *WM) createCursors() {
	font, err := xproto.NewFontId(wm.Conn)
	if err != nil {
		return
	}
	xproto.OpenFont(wm.Conn, font, uint16(len("cursor")), "cursor")

	// XC_left_ptr = 68, XC_sizing = 120, XC_fleur = 52
	cursorGlyphs := [CurLast]uint16{68, 120, 52}
	for i := 0; i < CurLast; i++ {
		wm.Cursors[i], _ = xproto.NewCursorId(wm.Conn)
		xproto.CreateGlyphCursor(wm.Conn, wm.Cursors[i], font, font,
			cursorGlyphs[i], cursorGlyphs[i]+1,
			0, 0, 0, 0xFFFF, 0xFFFF, 0xFFFF)
	}
	xproto.CloseFont(wm.Conn, font)
}

func (wm *WM) allocColors() {
	cmap := wm.Screen.DefaultColormap

	normColor := parseColor(config.ColBorderNorm)
	reply, err := xproto.AllocColor(wm.Conn, cmap,
		normColor[0], normColor[1], normColor[2]).Reply()
	if err == nil {
		wm.BorderNorm = reply.Pixel
	}

	selColor := parseColor(config.ColBorderSel)
	reply, err = xproto.AllocColor(wm.Conn, cmap,
		selColor[0], selColor[1], selColor[2]).Reply()
	if err == nil {
		wm.BorderSel = reply.Pixel
	}
}

func parseColor(hex string) [3]uint16 {
	hex = strings.TrimPrefix(hex, "#")
	var r, g, b uint16
	if len(hex) == 6 {
		fmt.Sscanf(hex, "%02x%02x%02x", &r, &g, &b)
		// X11 colors are 16-bit
		r = r * 257
		g = g * 257
		b = b * 257
	}
	return [3]uint16{r, g, b}
}

// xgbEvent bundles an X event with its accompanying protocol error.
type xgbEvent struct {
	ev  xgb.Event
	err xgb.Error
}

// startEventPump starts a goroutine that reads X events from the connection
// and delivers them to wm.XEvCh so the main loop can select between X events
// and IPC requests without ever blocking indefinitely.
func (wm *WM) startEventPump() {
	wm.XEvCh = make(chan xgbEvent, 64)
	go func() {
		for {
			ev, err := wm.Conn.WaitForEvent()
			wm.XEvCh <- xgbEvent{ev, err}
			// A nil ev and nil err signals connection closed.
			if ev == nil && err == nil {
				return
			}
		}
	}()
}

// Run is the main event loop.
func (wm *WM) Run(ipcServer *ipc.Server) {
	var ipcCh <-chan *ipc.IPCRequest
	if wm.QuitCh == nil {
		wm.QuitCh = make(chan struct{})
	}

	if ipcServer != nil {
		go ipcServer.Run()
		ipcCh = ipcServer.RequestChan()
	}

	wm.startEventPump()

	for wm.Running.Load() {
		// Drain all immediately-available X events before blocking.
	drainX:
		for {
			select {
			case <-wm.QuitCh:
				wm.Running.Store(false)
				return
			case xev := <-wm.XEvCh:
				wm.dispatchXEv(xev)
			default:
				break drainX
			}
		}
		wm.publishTagsIfChanged(ipcServer)

		// Block until either an X event or an IPC request arrives.
		if ipcCh != nil {
			select {
			case <-wm.QuitCh:
				wm.Running.Store(false)
				return
			case xev := <-wm.XEvCh:
				wm.dispatchXEv(xev)
			case req := <-ipcCh:
				resp := wm.handleIPCRequest(req)
				req.ResponseCh <- resp
			}
		} else {
			select {
			case <-wm.QuitCh:
				wm.Running.Store(false)
				return
			case xev := <-wm.XEvCh:
				wm.dispatchXEv(xev)
			}
		}

		// After each event, drain any remaining IPC requests (non-blocking).
		if ipcCh != nil {
		drainIPC:
			for {
				select {
				case <-wm.QuitCh:
					wm.Running.Store(false)
					return
				case req := <-ipcCh:
					resp := wm.handleIPCRequest(req)
					req.ResponseCh <- resp
				default:
					break drainIPC
				}
			}
		}
		wm.publishTagsIfChanged(ipcServer)
	}
}

// RequestQuit asks the WM event loop to stop exactly once.
func (wm *WM) RequestQuit() {
	if wm.QuitCh == nil {
		wm.QuitCh = make(chan struct{})
	}
	wm.quitOnce.Do(func() {
		wm.Running.Store(false)
		close(wm.QuitCh)
	})
}

func (wm *WM) dispatchXEv(xev xgbEvent) {
	if xev.ev != nil {
		wm.handleEvent(xev.ev)
	}
	if xev.err != nil {
		wm.handleXError(xev.err)
	}
}

func (wm *WM) handleXError(xerr xgb.Error) {
	// Log but don't die — matches C behavior of ignoring most X errors
	util.LogDebugf("X error: %v", xerr)
}

// Scan queries existing windows and manages them.
func (wm *WM) Scan() {
	reply, err := xproto.QueryTree(wm.Conn, wm.Root).Reply()
	if err != nil {
		return
	}

	// First pass: non-transient windows
	for _, win := range reply.Children {
		attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
		if err != nil || attrs.OverrideRedirect {
			continue
		}

		// Check if transient
		prop, err := xproto.GetProperty(wm.Conn, false, win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		if err == nil && prop.ValueLen > 0 {
			continue // handle transients in second pass
		}

		if attrs.MapState == xproto.MapStateViewable || wm.getState(win) == icccmIconicState {
			wm.manage(win, attrs)
		}
	}

	// Second pass: transient windows
	for _, win := range reply.Children {
		attrs, err := xproto.GetWindowAttributes(wm.Conn, win).Reply()
		if err != nil {
			continue
		}

		prop, err := xproto.GetProperty(wm.Conn, false, win,
			xproto.AtomWmTransientFor, xproto.AtomWindow, 0, 1).Reply()
		if err != nil || prop.ValueLen == 0 {
			continue
		}

		if attrs.MapState == xproto.MapStateViewable || wm.getState(win) == icccmIconicState {
			wm.manage(win, attrs)
		}
	}
}

const (
	icccmNormalState    = 1
	icccmIconicState    = 3
	icccmWithdrawnState = 0
)

// Startup runs startup commands.
func (wm *WM) Startup() {
	wm.SetDefaultWallpaper()

	if wm.NoConfig || wm.StartupPath == "" {
		return
	}
	if _, err := os.Stat(wm.StartupPath); err != nil {
		return
	}
	wm.spawnCmd([]string{"sh", wm.StartupPath})
}

// SetDefaultWallpaper sets ~/.config/sade/wp.jpg as the root background when present.
func (wm *WM) SetDefaultWallpaper() {
	if wm.Conn == nil || wm.Screen == nil || wm.Root == 0 {
		return
	}
	home := util.HomePath()
	if home == "" {
		return
	}
	path := filepath.Join(home, ".config", "sade", "wp.jpg")
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()

	src, _, err := image.Decode(file)
	if err != nil {
		util.LogDebug("wallpaper: decode %s failed: %v", path, err)
		return
	}
	w, h := wm.SW, wm.SH
	if w <= 0 || h <= 0 {
		w, h = int(wm.Screen.WidthInPixels), int(wm.Screen.HeightInPixels)
	}
	if w <= 0 || h <= 0 {
		return
	}

	visual, ok := wm.rootVisual()
	if !ok {
		util.LogDebug("wallpaper: root visual not found")
		return
	}
	format, ok := wm.pixmapFormat(wm.Screen.RootDepth)
	if !ok {
		util.LogDebug("wallpaper: pixmap format for depth %d not found", wm.Screen.RootDepth)
		return
	}

	pixmap, err := xproto.NewPixmapId(wm.Conn)
	if err != nil {
		util.LogDebug("wallpaper: create pixmap id failed: %v", err)
		return
	}
	if err := xproto.CreatePixmapChecked(wm.Conn, wm.Screen.RootDepth, pixmap,
		xproto.Drawable(wm.Root), uint16(w), uint16(h)).Check(); err != nil {
		util.LogDebug("wallpaper: create pixmap failed: %v", err)
		return
	}

	gc, err := xproto.NewGcontextId(wm.Conn)
	if err != nil {
		xproto.FreePixmap(wm.Conn, pixmap)
		util.LogDebug("wallpaper: create gc id failed: %v", err)
		return
	}
	if err := xproto.CreateGCChecked(wm.Conn, gc, xproto.Drawable(pixmap), 0, nil).Check(); err != nil {
		xproto.FreePixmap(wm.Conn, pixmap)
		util.LogDebug("wallpaper: create gc failed: %v", err)
		return
	}
	defer xproto.FreeGC(wm.Conn, gc)

	img := coverImage(src, w, h)
	if err := wm.putWallpaperImage(pixmap, gc, img, visual, format); err != nil {
		xproto.FreePixmap(wm.Conn, pixmap)
		util.LogDebug("wallpaper: upload failed: %v", err)
		return
	}

	if err := xproto.ChangeWindowAttributesChecked(wm.Conn, wm.Root, xproto.CwBackPixmap,
		[]uint32{uint32(pixmap)}).Check(); err != nil {
		xproto.FreePixmap(wm.Conn, pixmap)
		util.LogDebug("wallpaper: set root background failed: %v", err)
		return
	}
	if err := wm.publishRootPixmap(pixmap); err != nil {
		xproto.FreePixmap(wm.Conn, pixmap)
		util.LogDebug("wallpaper: publish root pixmap failed: %v", err)
		return
	}

	oldPixmap := wm.WallpaperPixmap
	wm.WallpaperPixmap = pixmap
	xproto.ClearArea(wm.Conn, false, wm.Root, 0, 0, 0, 0)
	if oldPixmap != 0 {
		xproto.FreePixmap(wm.Conn, oldPixmap)
	}
	wm.Conn.Sync()
}

func (wm *WM) publishRootPixmap(pixmap xproto.Pixmap) error {
	for _, name := range []string{"_XROOTPMAP_ID", "ESETROOT_PMAP_ID"} {
		reply, err := xproto.InternAtom(wm.Conn, false, uint16(len(name)), name).Reply()
		if err != nil {
			return err
		}
		if err := xproto.ChangePropertyChecked(wm.Conn, xproto.PropModeReplace, wm.Root,
			reply.Atom, xproto.AtomPixmap, 32, 1, uint32ToBytes(uint32(pixmap))).Check(); err != nil {
			return err
		}
	}
	return nil
}

func coverImage(src image.Image, width, height int) *image.RGBA {
	dst := image.NewRGBA(image.Rect(0, 0, width, height))
	sb := src.Bounds()
	sw, sh := sb.Dx(), sb.Dy()
	if sw <= 0 || sh <= 0 {
		return dst
	}

	scaleX := float64(sw) / float64(width)
	scaleY := float64(sh) / float64(height)
	scale := scaleX
	if scaleY < scale {
		scale = scaleY
	}
	sampleW := float64(width) * scale
	sampleH := float64(height) * scale
	offsetX := (float64(sw) - sampleW) / 2
	offsetY := (float64(sh) - sampleH) / 2

	for y := 0; y < height; y++ {
		sy := sb.Min.Y + int(offsetY+(float64(y)+0.5)*scale)
		if sy >= sb.Max.Y {
			sy = sb.Max.Y - 1
		}
		for x := 0; x < width; x++ {
			sx := sb.Min.X + int(offsetX+(float64(x)+0.5)*scale)
			if sx >= sb.Max.X {
				sx = sb.Max.X - 1
			}
			dst.Set(x, y, src.At(sx, sy))
		}
	}

	return dst
}

func (wm *WM) putWallpaperImage(pixmap xproto.Pixmap, gc xproto.Gcontext, img *image.RGBA, visual xproto.VisualInfo, format xproto.Format) error {
	b := img.Bounds()
	width, height := b.Dx(), b.Dy()
	bytesPerPixel := int(format.BitsPerPixel) / 8
	if bytesPerPixel <= 0 {
		return fmt.Errorf("invalid bits per pixel %d", format.BitsPerPixel)
	}
	scanlinePadBytes := int(format.ScanlinePad) / 8
	if scanlinePadBytes <= 0 {
		scanlinePadBytes = 4
	}
	bytesPerLine := align(width*bytesPerPixel, scanlinePadBytes)
	if bytesPerLine <= 0 {
		return fmt.Errorf("invalid bytes per line")
	}

	setup := xproto.Setup(wm.Conn)
	maxRequestBytes := int(setup.MaximumRequestLength)*4 - 24
	if maxRequestBytes <= 0 {
		maxRequestBytes = 262140 - 24
	}
	rowsPerChunk := maxRequestBytes / bytesPerLine
	if rowsPerChunk < 1 {
		return fmt.Errorf("wallpaper row is too wide for one X request")
	}

	for y := 0; y < height; y += rowsPerChunk {
		rows := rowsPerChunk
		if y+rows > height {
			rows = height - y
		}
		data := make([]byte, bytesPerLine*rows)
		for row := 0; row < rows; row++ {
			srcY := y + row
			for x := 0; x < width; x++ {
				i := img.PixOffset(x, srcY)
				pixel := packPixel(img.Pix[i], img.Pix[i+1], img.Pix[i+2], visual)
				writePixel(data[row*bytesPerLine+x*bytesPerPixel:], pixel, bytesPerPixel, setup.ImageByteOrder)
			}
		}
		err := xproto.PutImageChecked(wm.Conn, xproto.ImageFormatZPixmap, xproto.Drawable(pixmap), gc,
			uint16(width), uint16(rows), 0, int16(y), 0, wm.Screen.RootDepth, data).Check()
		if err != nil {
			return err
		}
	}
	return nil
}

func (wm *WM) rootVisual() (xproto.VisualInfo, bool) {
	for _, depth := range wm.Screen.AllowedDepths {
		for _, visual := range depth.Visuals {
			if visual.VisualId == wm.Screen.RootVisual {
				return visual, true
			}
		}
	}
	return xproto.VisualInfo{}, false
}

func (wm *WM) pixmapFormat(depth byte) (xproto.Format, bool) {
	for _, format := range xproto.Setup(wm.Conn).PixmapFormats {
		if format.Depth == depth {
			return format, true
		}
	}
	return xproto.Format{}, false
}

func packPixel(r, g, b byte, visual xproto.VisualInfo) uint32 {
	return scaleToMask(r, visual.RedMask) |
		scaleToMask(g, visual.GreenMask) |
		scaleToMask(b, visual.BlueMask)
}

func scaleToMask(value byte, mask uint32) uint32 {
	if mask == 0 {
		return 0
	}
	shift := 0
	for ((mask >> shift) & 1) == 0 {
		shift++
	}
	bits := 0
	for ((mask >> (shift + bits)) & 1) == 1 {
		bits++
	}
	max := uint32((1 << bits) - 1)
	return ((uint32(value)*max + 127) / 255) << shift
}

func writePixel(dst []byte, pixel uint32, bytesPerPixel int, byteOrder byte) {
	if byteOrder == xproto.ImageOrderMSBFirst {
		for i := 0; i < bytesPerPixel; i++ {
			shift := uint((bytesPerPixel - 1 - i) * 8)
			dst[i] = byte(pixel >> shift)
		}
		return
	}
	for i := 0; i < bytesPerPixel; i++ {
		dst[i] = byte(pixel >> uint(i*8))
	}
}

func align(n, alignment int) int {
	if alignment <= 1 {
		return n
	}
	remainder := n % alignment
	if remainder == 0 {
		return n
	}
	return n + alignment - remainder
}

func (wm *WM) ApplyDisplaySettings() {
	if wm.NoConfig || wm.SettingsPath == "" {
		return
	}
	settings := config.LoadSettingsTOML(wm.SettingsPath)
	if settings == nil || settings.Display == nil {
		return
	}

	query, err := exec.Command("xrandr", "--query").Output()
	if err != nil {
		util.LogDebug("display settings: xrandr query failed: %v", err)
		return
	}
	args, ok := config.BuildXrandrArgs(settings.Display, string(query))
	if !ok {
		return
	}
	if err := exec.Command("xrandr", args...).Run(); err != nil {
		util.LogDebug("display settings: xrandr apply failed: %v", err)
		return
	}
	wm.refreshRootGeometry()
	wm.updateGeom()
	wm.recomputeWorkAreas()
	wm.Arrange(nil)
}

func (wm *WM) refreshRootGeometry() {
	if wm.Conn == nil || wm.Root == 0 {
		return
	}
	geom, err := xproto.GetGeometry(wm.Conn, xproto.Drawable(wm.Root)).Reply()
	if err != nil {
		return
	}
	wm.SW = int(geom.Width)
	wm.SH = int(geom.Height)
}

// Cleanup tears down the WM.
func (wm *WM) Cleanup() {
	// View all tags
	wm.View(&config.Arg{UI: ^uint32(0)})

	// Set a no-op layout
	noopLayout := config.Layout{Symbol: "", Arrange: nil}
	wm.SelMon.Lt = &noopLayout

	// Unmanage all windows
	for m := wm.Mons; m != nil; m = m.Next {
		for m.Stack != nil {
			wm.unmanage(m.Stack, false)
		}
	}

	// Ungrab keys
	xproto.UngrabKey(wm.Conn, xproto.GrabAny, wm.Root, xproto.ModMaskAny)

	// Free monitors
	wm.Mons = nil

	// Free cursors
	for i := 0; i < CurLast; i++ {
		xproto.FreeCursor(wm.Conn, wm.Cursors[i])
	}

	// Destroy check window
	xproto.DestroyWindow(wm.Conn, wm.WMCheckWin)

	if wm.WallpaperPixmap != 0 {
		for _, name := range []string{"_XROOTPMAP_ID", "ESETROOT_PMAP_ID"} {
			if reply, err := xproto.InternAtom(wm.Conn, true, uint16(len(name)), name).Reply(); err == nil && reply.Atom != xproto.AtomNone {
				xproto.DeleteProperty(wm.Conn, wm.Root, reply.Atom)
			}
		}
		xproto.ChangeWindowAttributes(wm.Conn, wm.Root, xproto.CwBackPixmap, []uint32{xproto.BackPixmapNone})
		xproto.FreePixmap(wm.Conn, wm.WallpaperPixmap)
		wm.WallpaperPixmap = 0
	}

	xproto.SetInputFocus(wm.Conn, xproto.InputFocusPointerRoot, xproto.InputFocusPointerRoot, xproto.TimeCurrentTime)
	xproto.DeleteProperty(wm.Conn, wm.Root, wm.NetAtom[NetActiveWindow])
}

// SetTopOffset adjusts the working area of all monitors.
func (wm *WM) SetTopOffset(offset uint) {
	wm.TopOffset = offset
	wm.recomputeWorkAreas()
	wm.Arrange(nil)
}

// SetBottomOffset adjusts the working area of all monitors.
func (wm *WM) SetBottomOffset(offset uint) {
	wm.BottomOffset = offset
	wm.recomputeWorkAreas()
	wm.Arrange(nil)
}

func (wm *WM) recomputeWorkAreas() {
	for m := wm.Mons; m != nil; m = m.Next {
		wm.recomputeWorkArea(m)
	}
}

func (wm *WM) recomputeWorkArea(m *Monitor) {
	if m == nil {
		return
	}
	top := min(int(wm.TopOffset), m.MH)
	bottom := min(int(wm.BottomOffset), max(0, m.MH-top))
	m.WX = m.MX
	m.WY = m.MY + top
	m.WW = m.MW
	m.WH = max(1, m.MH-top-bottom)
}

// DebugInfo returns a multi-line string with a snapshot of WM internal state.
// Intended for use in the SIGUSR1 handler together with a goroutine stack dump.
func (wm *WM) DebugInfo() string {
	var b strings.Builder
	b.WriteString("=== sadewm debug snapshot ===\n")
	fmt.Fprintf(&b, "dragging:     %v\n", wm.dragging)
	fmt.Fprintf(&b, "running:      %v\n", wm.Running.Load())
	fmt.Fprintf(&b, "pendingEvts:  %d\n", len(wm.pendingEvts))
	fmt.Fprintf(&b, "XEvCh len:    %d\n", len(wm.XEvCh))
	monIdx := 0
	for m := wm.Mons; m != nil; m = m.Next {
		nClients := 0
		for c := m.Clients; c != nil; c = c.Next {
			nClients++
		}
		selName := ""
		if m.Sel != nil {
			selName = m.Sel.Name
		}
		fmt.Fprintf(&b, "monitor[%d]:   tags=0x%04x clients=%d sel=%q layout=%s\n",
			monIdx, m.TagSet[m.SelTags], nClients, selName, m.LtSymbol)
		monIdx++
	}
	return b.String()
}

// Helper: uint32 to little-endian bytes
func uint32ToBytes(v uint32) []byte {
	b := make([]byte, 4)
	putUint32(b, v)
	return b
}

func putUint32(b []byte, v uint32) {
	b[0] = byte(v)
	b[1] = byte(v >> 8)
	b[2] = byte(v >> 16)
	b[3] = byte(v >> 24)
}

func getUint32(b []byte) uint32 {
	return uint32(b[0]) | uint32(b[1])<<8 | uint32(b[2])<<16 | uint32(b[3])<<24
}

// handleIPCRequest processes an IPC request from the socket server.
func (wm *WM) handleIPCRequest(req *ipc.IPCRequest) *ipc.Response {
	switch req.Cmd {
	case "get_state":
		return wm.ipcGetState()
	case "tags_state":
		return wm.ipcTagsState()
	case "keybinds":
		return wm.ipcKeybinds()
	case "subscribe_tags":
		mask, states := wm.currentTagsState()
		return &ipc.Response{OK: true, TagMask: mask, TagsState: states}
	case "view":
		wm.View(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "toggleview":
		wm.ToggleView(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "tag":
		wm.Tag(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "toggletag":
		wm.ToggleTag(&config.Arg{UI: req.Mask})
		return &ipc.Response{OK: true}
	case "reload":
		wm.ReloadConfig(nil)
		return &ipc.Response{OK: true}
	case "quit":
		wm.Quit(nil)
		return &ipc.Response{OK: true}
	case "open-launcher":
		wm.spawnCmd([]string{"sadeshell", "--open-launcher"})
		return &ipc.Response{OK: true}
	case "open-keybinds":
		wm.spawnCmd([]string{"sadeshell", "--open-keybinds"})
		return &ipc.Response{OK: true}
	case "open-emoji-picker":
		wm.spawnCmd([]string{"sadeshell", "--open-emoji-picker"})
		return &ipc.Response{OK: true}
	case "open-window-picker":
		wm.spawnCmd([]string{"sadeshell", "--open-window-picker"})
		return &ipc.Response{OK: true}
	case "open-minimized-picker":
		wm.spawnCmd([]string{"sadeshell", "--open-minimized-picker"})
		return &ipc.Response{OK: true}
	case "get_clients":
		return wm.ipcGetClients()
	case "focus_window":
		return wm.ipcFocusWindow(req.WinID)
	default:
		return &ipc.Response{OK: false, Error: "unknown command"}
	}
}

func (wm *WM) ipcGetState() *ipc.Response {
	resp := &ipc.Response{
		OK:        true,
		TagMask:   wm.SelMon.TagSet[wm.SelMon.SelTags],
		Layout:    wm.SelMon.Lt.Symbol,
		MFact:     float64(wm.SelMon.MFact),
		NMaster:   wm.SelMon.NMaster,
		Gaps:      wm.SelMon.GapPx,
		RightTile: wm.SelMon.IsRightTiled,
		Clients:   []ipc.ClientDTO{},
	}

	for c := wm.SelMon.Clients; c != nil; c = c.Next {
		resp.Clients = append(resp.Clients, ipc.ClientDTO{
			Name:      c.Name,
			WinID:     uint32(c.Win),
			Class:     wm.getWMClass(c.Win),
			Tags:      c.Tags,
			Floating:  c.IsFloating,
			Maximized: c.Maximized,
			Focused:   c == wm.SelMon.Sel,
			Minimized: c.Minimized,
		})
	}

	return resp
}

func (wm *WM) ipcTagsState() *ipc.Response {
	_, states := wm.currentTagsState()
	return &ipc.Response{OK: true, TagsState: states}
}

func (wm *WM) currentTagsState() (uint32, []string) {
	var occ, urg uint32
	for c := wm.SelMon.Clients; c != nil; c = c.Next {
		if c.Tags&TagMask() != TagMask() {
			occ |= c.Tags
			if c.IsUrgent {
				urg |= c.Tags
			}
		}
	}

	states := make([]string, len(config.Tags))
	for i := range config.Tags {
		bit := uint32(1 << i)
		switch {
		case urg&bit != 0:
			states[i] = "U"
		case wm.SelMon.TagSet[wm.SelMon.SelTags]&bit != 0:
			states[i] = "A"
		case occ&bit != 0:
			states[i] = "O"
		default:
			states[i] = "I"
		}
	}

	return wm.SelMon.TagSet[wm.SelMon.SelTags], states
}

func (wm *WM) publishTagsIfChanged(ipcServer *ipc.Server) {
	if ipcServer == nil || wm.SelMon == nil {
		return
	}
	mask, states := wm.currentTagsState()
	if wm.lastTagsSnapshotValid &&
		wm.lastTagMask == mask &&
		stringSlicesEqual(wm.lastTagsState, states) {
		return
	}

	wm.lastTagMask = mask
	wm.lastTagsState = append(wm.lastTagsState[:0], states...)
	wm.lastTagsSnapshotValid = true

	ipcServer.BroadcastTags(ipc.TagEvent{
		Event:     "tags_state",
		TagMask:   mask,
		TagsState: states,
	})
}

func stringSlicesEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// ipcGetClients returns all managed clients across all tags (all monitors).
// Dock windows, override-redirect windows, and minimized windows that are
// purely system windows are included only if they pass the IsDock check.
func (wm *WM) ipcGetClients() *ipc.Response {
	clients := []ipc.ClientDTO{}
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.IsDock {
				continue
			}
			clients = append(clients, ipc.ClientDTO{
				Name:      c.Name,
				WinID:     uint32(c.Win),
				Class:     wm.getWMClass(c.Win),
				Tags:      c.Tags,
				Floating:  c.IsFloating,
				Maximized: c.Maximized,
				Focused:   c == m.Sel,
				Minimized: c.Minimized,
			})
		}
	}
	return &ipc.Response{OK: true, Clients: clients}
}

// ipcFocusWindow switches to the tag containing the given window and focuses it.
func (wm *WM) ipcFocusWindow(winID uint32) *ipc.Response {
	if winID == 0 {
		return &ipc.Response{OK: false, Error: "invalid win_id"}
	}
	target := xproto.Window(winID)

	// Find the client across all monitors
	var found *Client
	for m := wm.Mons; m != nil; m = m.Next {
		for c := m.Clients; c != nil; c = c.Next {
			if c.Win == target {
				found = c
				break
			}
		}
		if found != nil {
			break
		}
	}

	if found == nil {
		return &ipc.Response{OK: false, Error: "window not found"}
	}

	// Switch selected monitor to the one that owns this client
	if found.Mon != wm.SelMon {
		wm.Unfocus(wm.SelMon.Sel, true)
		wm.SelMon = found.Mon
	}

	// Switch to the client's tag (use the lowest-numbered tag the client is on)
	clientTags := found.Tags & TagMask()
	if clientTags != 0 {
		// Pick lowest bit tag
		tagMask := clientTags & (^clientTags + 1)
		wm.SelMon.SelTags ^= 1
		wm.SelMon.TagSet[wm.SelMon.SelTags] = tagMask
		wm.ApplyTag(wm.GetDomTag(wm.SelMon.Tags))
	}

	// If minimized, restore it
	if found.Minimized {
		// Remove from minimize stack if present
		for i, mc := range wm.MinimizeStack {
			if mc == found {
				wm.MinimizeStack = append(wm.MinimizeStack[:i], wm.MinimizeStack[i+1:]...)
				break
			}
		}
		found.Minimized = false
		if found.IsFloating {
			wm.showTitlebar(found)
			wm.raiseTitlebar(found)
		}
	}

	wm.Focus(found)
	wm.Restack(found.Mon)
	wm.Arrange(found.Mon)
	return &ipc.Response{OK: true}
}

// getWMClass returns the WM_CLASS string (second part = class name) for a window.
func (wm *WM) getWMClass(w xproto.Window) string {
	reply, err := xproto.GetProperty(wm.Conn, false, w,
		xproto.AtomWmClass, xproto.AtomString, 0, 256).Reply()
	if err != nil || reply.ValueLen == 0 {
		return ""
	}
	parts := splitWMClass(reply.Value)
	if len(parts) >= 2 {
		return parts[1]
	}
	if len(parts) == 1 {
		return parts[0]
	}
	return ""
}
