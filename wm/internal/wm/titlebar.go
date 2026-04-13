package wm

// Titlebar implementation for floating windows.
//
// Uses Cairo (via CGo) to render a header
// bar that matches the sadeshell aesthetic: dark navy background, three
// traffic-light buttons on the left (close / stay-on-top / minimize) and the
// window title centred.  Dragging the non-button area moves the window.

/*
#cgo pkg-config: cairo x11 xext
#include <X11/Xlib.h>
#include <X11/extensions/shape.h>
#include <cairo/cairo.h>
#include <cairo/cairo-xlib.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// ── runtime colour table (filled from Go config vars) ─────────────────────────
typedef struct {
    double bg_r,   bg_g,   bg_b;    // normal background
    double bgf_r,  bgf_g,  bgf_b;   // focused background
    double sep_r,  sep_g,  sep_b;   // bottom separator
    double txt_r,  txt_g,  txt_b;   // title text
    double cls_r,  cls_g,  cls_b;   // close button
    double abv_r,  abv_g,  abv_b;   // stay-on-top button (active)
    double abv_dim;                  // stay-on-top alpha when inactive
    double min_r,  min_g,  min_b;   // minimize button
} TBColors;

// Button layout constants (compile-time; not user-configurable)
#define TB_BTN_R        6.0
#define TB_BTN_FIRST_X  16
#define TB_BTN_STEP     20
#define TB_ROUND_RADIUS  6.0

// Open an Xlib display connection.  Returns NULL on failure.
static Display* tb_open_display(const char* name) {
    return XOpenDisplay(name);
}

// Non-fatal X error handler so that Cairo RENDER errors (e.g. freeing a
// picture for a destroyed window) do not kill the WM via exit(1).
static int tb_xerror_handler(Display *dpy, XErrorEvent *ev) {
    (void)dpy; (void)ev;
    return 0;
}

static void tb_install_error_handler() {
    XSetErrorHandler(tb_xerror_handler);
}

// Apply a rounded-top-corner shape mask to the titlebar window.
static void tb_apply_rounded_shape(Display *dpy, Window win, int w, int h) {
    double r = TB_ROUND_RADIUS;
    Pixmap mask = XCreatePixmap(dpy, win, w, h, 1);
    if (!mask) return;
    Screen *screen = DefaultScreenOfDisplay(dpy);
    cairo_surface_t *ms = cairo_xlib_surface_create_for_bitmap(dpy, mask, screen, w, h);
    if (!ms) { XFreePixmap(dpy, mask); return; }
    cairo_t *cr = cairo_create(ms);
    if (!cr) { cairo_surface_destroy(ms); XFreePixmap(dpy, mask); return; }
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_source_rgba(cr, 1, 1, 1, 1);
    cairo_new_path(cr);
    cairo_arc(cr, r,     r, r, M_PI,     3*M_PI/2);
    cairo_arc(cr, w - r, r, r, -M_PI/2,  0);
    cairo_line_to(cr, w, h);
    cairo_line_to(cr, 0, h);
    cairo_close_path(cr);
    cairo_fill(cr);
    cairo_destroy(cr);
    cairo_surface_finish(ms);
    cairo_surface_destroy(ms);
    XShapeCombineMask(dpy, win, ShapeBounding, 0, 0, mask, ShapeSet);
    XFreePixmap(dpy, mask);
    XFlush(dpy);
}

// Draw the titlebar.
//   hover_btn: 1=close, 2=above, 3=minimize, 0=none
static void tb_draw(Display *dpy, unsigned long win,
                    int w, int h,
                    const char *title,
                    int focused, int is_above, int hover_btn,
                    TBColors *col) {
    Visual *visual = XDefaultVisual(dpy, DefaultScreen(dpy));
    cairo_surface_t *surface = cairo_xlib_surface_create(
        dpy, (Drawable)win, visual, w, h);
    if (!surface) return;
    cairo_t *cr = cairo_create(surface);
    if (!cr) { cairo_surface_destroy(surface); return; }

    // ── rounded background ────────────────────────────────────────────────────
    if (focused)
        cairo_set_source_rgb(cr, col->bgf_r, col->bgf_g, col->bgf_b);
    else
        cairo_set_source_rgb(cr, col->bg_r,  col->bg_g,  col->bg_b);
    {
        double r = TB_ROUND_RADIUS;
        cairo_new_path(cr);
        cairo_arc(cr, r,     r, r, M_PI,    3*M_PI/2);
        cairo_arc(cr, w - r, r, r, -M_PI/2, 0);
        cairo_line_to(cr, w, h);
        cairo_line_to(cr, 0, h);
        cairo_close_path(cr);
        cairo_fill(cr);
    }

    // ── bottom separator ──────────────────────────────────────────────────────
    cairo_set_source_rgb(cr, col->sep_r, col->sep_g, col->sep_b);
    cairo_set_line_width(cr, 1.0);
    cairo_move_to(cr, 0,   h - 0.5);
    cairo_line_to(cr, w,   h - 0.5);
    cairo_stroke(cr);

    // ── buttons ───────────────────────────────────────────────────────────────
    double by = h / 2.0;

    // Close
    double cx0 = TB_BTN_FIRST_X;
    cairo_arc(cr, cx0, by, TB_BTN_R, 0, 2*M_PI);
    cairo_set_source_rgb(cr, col->cls_r, col->cls_g, col->cls_b);
    cairo_fill(cr);
    if (hover_btn == 1) {
        double ic = TB_BTN_R * 0.50;
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx0-ic, by-ic); cairo_line_to(cr, cx0+ic, by+ic); cairo_stroke(cr);
        cairo_move_to(cr, cx0+ic, by-ic); cairo_line_to(cr, cx0-ic, by+ic); cairo_stroke(cr);
    }

    // Stay-on-top
    double cx1 = TB_BTN_FIRST_X + TB_BTN_STEP;
    cairo_arc(cr, cx1, by, TB_BTN_R, 0, 2*M_PI);
    if (is_above)
        cairo_set_source_rgb(cr,  col->abv_r, col->abv_g, col->abv_b);
    else
        cairo_set_source_rgba(cr, col->abv_r, col->abv_g, col->abv_b, col->abv_dim);
    cairo_fill(cr);
    if (hover_btn == 2) {
        double aw = TB_BTN_R * 0.55, ah = TB_BTN_R * 0.50;
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx1 - aw, by + ah * 0.4);
        cairo_line_to(cr, cx1,       by - ah * 0.8);
        cairo_line_to(cr, cx1 + aw, by + ah * 0.4);
        cairo_stroke(cr);
    }

    // Minimize
    double cx2 = TB_BTN_FIRST_X + 2*TB_BTN_STEP;
    cairo_arc(cr, cx2, by, TB_BTN_R, 0, 2*M_PI);
    cairo_set_source_rgb(cr, col->min_r, col->min_g, col->min_b);
    cairo_fill(cr);
    if (hover_btn == 3) {
        double hw = TB_BTN_R * 0.55;
        cairo_set_source_rgba(cr, 1.0, 1.0, 1.0, 0.90);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx2-hw, by); cairo_line_to(cr, cx2+hw, by); cairo_stroke(cr);
    }

    // ── window title ──────────────────────────────────────────────────────────
    if (title && title[0] != '\0') {
        cairo_set_source_rgb(cr, col->txt_r, col->txt_g, col->txt_b);
        cairo_select_font_face(cr, "Sans",
            CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
        cairo_set_font_size(cr, 12.0);
        cairo_text_extents_t ext;
        cairo_text_extents(cr, title, &ext);
        double max_w = (double)(w - 70 - 10);
        double tx;
        if (ext.width > max_w) {
            tx = 70;
        } else {
            tx = (w - ext.width) / 2.0 - ext.x_bearing;
            if (tx < 70) tx = 70;
        }
        double ty = (h - ext.height) / 2.0 - ext.y_bearing;
        cairo_move_to(cr, tx, ty);
        cairo_show_text(cr, title);
    }

    cairo_surface_flush(surface);
    XFlush(dpy);
    cairo_destroy(cr);
    cairo_surface_destroy(surface);
}
*/
import "C"

import (
	"fmt"
	"os"
	"unsafe"

	"github.com/BurntSushi/xgb/xproto"

	"github.com/sadewm/sadewm/wm/internal/config"
)

const titlebarHeight = 28

// titleButton identifies which part of the titlebar was clicked.
type titleButton int

const (
	tbNone     titleButton = iota
	tbClose                // close / kill
	tbAbove                // toggle stay-on-top
	tbMinimize             // minimize
	tbDragArea             // bare area → drag window
)

// ── Xlib display ──────────────────────────────────────────────────────────────

// initXlibDpy opens an auxiliary Xlib connection used solely for Cairo
// rendering.  The main xgb connection cannot be used with Cairo's Xlib backend
// because Cairo needs a *C.Display pointer.
func (wm *WM) initXlibDpy() {
	dname := os.Getenv("DISPLAY")
	if dname == "" {
		dname = ":0"
	}
	cname := C.CString(dname)
	defer C.free(unsafe.Pointer(cname))
	dpy := C.tb_open_display(cname)
	if dpy == nil {
		return
	}
	// Install a non-fatal error handler so X errors (e.g. RenderBadPicture
	// when a window is destroyed while Cairo still holds a reference) do not
	// call exit(1) via Xlib's default handler.
	C.tb_install_error_handler()
	wm.XlibDpy = unsafe.Pointer(dpy)
}

// ── Titlebar map ──────────────────────────────────────────────────────────────

// titlebarToClient returns the client that owns the given titlebar window,
// or nil if the window is not a titlebar.
func (wm *WM) titlebarToClient(win xproto.Window) *Client {
	if wm.TitlebarMap == nil {
		return nil
	}
	return wm.TitlebarMap[win]
}

// ── Create / destroy ──────────────────────────────────────────────────────────

// createTitlebar creates a companion titlebar window above a floating client.
func (wm *WM) createTitlebar(c *Client) {
	if c.TitleWin != 0 || c.IsDock || c.IsFullscreen {
		return
	}
	if wm.XlibDpy == nil {
		return
	}

	tbX, tbY, tbW, tbH := wm.titlebarGeom(c)

	win, err := xproto.NewWindowId(wm.Conn)
	if err != nil {
		return
	}

	// OverrideRedirect so the WM doesn't try to manage the titlebar itself.
	mask := uint32(xproto.CwBackPixel | xproto.CwEventMask | xproto.CwOverrideRedirect)
	vals := []uint32{
		0x1a1b26, // background colour (#1a1b26) – Cairo will overwrite on expose
		1,        // OverrideRedirect = true
		uint32(xproto.EventMaskExposure | xproto.EventMaskButtonPress | xproto.EventMaskButtonRelease |
			xproto.EventMaskPointerMotion | xproto.EventMaskLeaveWindow),
	}
	// CreateWindow: depth=0 means copy-from-parent; border-width=0 (no border)
	xproto.CreateWindow(wm.Conn, 0,
		win, wm.Root,
		int16(tbX), int16(tbY), uint16(tbW), uint16(tbH),
		0,
		xproto.WindowClassInputOutput,
		xproto.WindowNone,
		mask, vals)

	xproto.MapWindow(wm.Conn, win)
	c.TitleWin = win

	// Remove the client window's X11 border — the titlebar acts as the frame.
	c.BW = 0
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowBorderWidth, []uint32{0})

	if wm.TitlebarMap == nil {
		wm.TitlebarMap = make(map[xproto.Window]*Client)
	}
	wm.TitlebarMap[win] = c

	// Apply rounded top-corner shape before first draw.
	wm.applyTitlebarShape(c)

	// Raise above the application window so it's always visible.
	xproto.ConfigureWindow(wm.Conn, win,
		xproto.ConfigWindowSibling|xproto.ConfigWindowStackMode,
		[]uint32{uint32(c.Win), uint32(xproto.StackModeAbove)})

	wm.drawTitlebar(c)
}

// destroyTitlebar unmaps and destroys the titlebar window for client c.
func (wm *WM) destroyTitlebar(c *Client) {
	if c.TitleWin == 0 {
		return
	}
	delete(wm.TitlebarMap, c.TitleWin)
	xproto.DestroyWindow(wm.Conn, c.TitleWin)
	c.TitleWin = 0
	// Restore the client border.
	c.BW = int(config.BorderPx)
	xproto.ConfigureWindow(wm.Conn, c.Win,
		xproto.ConfigWindowBorderWidth, []uint32{uint32(c.BW)})
}

// ── Geometry helpers ──────────────────────────────────────────────────────────

// titlebarGeom returns the position and size for c's titlebar window.
// The titlebar sits immediately above the client window (outside the border).
func (wm *WM) titlebarGeom(c *Client) (x, y, w, h int) {
	x = c.X - c.BW
	y = c.Y - titlebarHeight - c.BW
	w = c.W + 2*c.BW
	h = titlebarHeight
	if w < 1 {
		w = 1
	}
	return
}

// moveTitlebar repositions the titlebar to track the current client geometry.
func (wm *WM) moveTitlebar(c *Client) {
	if c.TitleWin == 0 {
		return
	}
	tbX, tbY, tbW, tbH := wm.titlebarGeom(c)
	xproto.ConfigureWindow(wm.Conn, c.TitleWin,
		xproto.ConfigWindowX|xproto.ConfigWindowY|
			xproto.ConfigWindowWidth|xproto.ConfigWindowHeight,
		[]uint32{uint32(tbX), uint32(tbY), uint32(tbW), uint32(tbH)})
	// Reapply shape mask since width may have changed.
	wm.applyTitlebarShape(c)
}

// showTitlebar maps the titlebar window (making it visible).
func (wm *WM) showTitlebar(c *Client) {
	if c.TitleWin == 0 {
		return
	}
	tbX, tbY, tbW, _ := wm.titlebarGeom(c)
	xproto.ConfigureWindow(wm.Conn, c.TitleWin,
		xproto.ConfigWindowX|xproto.ConfigWindowY|xproto.ConfigWindowWidth,
		[]uint32{uint32(tbX), uint32(tbY), uint32(tbW)})
	xproto.MapWindow(wm.Conn, c.TitleWin)
}

// hideTitlebar moves the titlebar off-screen (same trick used for minimized
// client windows) without destroying it.
func (wm *WM) hideTitlebar(c *Client) {
	if c.TitleWin == 0 {
		return
	}
	xproto.ConfigureWindow(wm.Conn, c.TitleWin,
		xproto.ConfigWindowX,
		[]uint32{uint32(c.Width() * -2)})
}

// raiseTitlebar stacks the titlebar above its client window.
func (wm *WM) raiseTitlebar(c *Client) {
	if c.TitleWin == 0 {
		return
	}
	xproto.ConfigureWindow(wm.Conn, c.TitleWin,
		xproto.ConfigWindowSibling|xproto.ConfigWindowStackMode,
		[]uint32{uint32(c.Win), uint32(xproto.StackModeAbove)})
}

// ── Cairo rendering ───────────────────────────────────────────────────────────

// hexToRGB converts a "#rrggbb" string to [0,1] float64 components.
func hexToRGB(hex string) (r, g, b float64) {
	if len(hex) > 0 && hex[0] == '#' {
		hex = hex[1:]
	}
	if len(hex) == 6 {
		var ri, gi, bi int
		fmt.Sscanf(hex, "%02x%02x%02x", &ri, &gi, &bi)
		return float64(ri) / 255.0, float64(gi) / 255.0, float64(bi) / 255.0
	}
	return 0, 0, 0
}

// tbColors builds a C.TBColors struct from the current config globals.
func tbColors() C.TBColors {
	var col C.TBColors
	col.bg_r, col.bg_g, col.bg_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarBgNorm)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.bgf_r, col.bgf_g, col.bgf_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarBgFocus)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.sep_r, col.sep_g, col.sep_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarSep)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.txt_r, col.txt_g, col.txt_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarText)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.cls_r, col.cls_g, col.cls_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarClose)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.abv_r, col.abv_g, col.abv_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarAbove)
		return C.double(r), C.double(g), C.double(b)
	}()
	col.abv_dim = 0.45
	col.min_r, col.min_g, col.min_b = func() (C.double, C.double, C.double) {
		r, g, b := hexToRGB(config.TitlebarMinimize)
		return C.double(r), C.double(g), C.double(b)
	}()
	return col
}

// applyTitlebarShape applies the X SHAPE extension rounded-top-corner mask.
func (wm *WM) applyTitlebarShape(c *Client) {
	if c.TitleWin == 0 || wm.XlibDpy == nil {
		return
	}
	_, _, tbW, tbH := wm.titlebarGeom(c)
	C.tb_apply_rounded_shape(
		(*C.Display)(wm.XlibDpy),
		C.ulong(c.TitleWin),
		C.int(tbW),
		C.int(tbH),
	)
}

// drawTitlebar renders the titlebar using Cairo.
func (wm *WM) drawTitlebar(c *Client) {
	if c.TitleWin == 0 || wm.XlibDpy == nil {
		return
	}

	_, _, tbW, tbH := wm.titlebarGeom(c)

	focused := c == wm.SelMon.Sel
	cTitle := C.CString(c.Name)
	defer C.free(unsafe.Pointer(cTitle))

	col := tbColors()
	C.tb_draw(
		(*C.Display)(wm.XlibDpy),
		C.ulong(c.TitleWin),
		C.int(tbW),
		C.int(tbH),
		cTitle,
		boolToInt(focused),
		boolToInt(c.IsAbove),
		C.int(c.TitleHover),
		&col,
	)
}

func boolToInt(b bool) C.int {
	if b {
		return 1
	}
	return 0
}

// ── Hit testing ───────────────────────────────────────────────────────────────

// hitTestTitlebar returns which logical area of the titlebar was clicked at
// pixel coordinate (ex, ey) relative to the titlebar window origin.
func hitTestTitlebar(ex, ey int) titleButton {
	const (
		btnY     = titlebarHeight / 2 // vertical centre
		btnFirst = 16                 // first button centre X
		btnStep  = 20                 // step between button centres
		btnHit   = 9                  // click radius (slightly larger than drawn radius)
	)
	type btnSpec struct {
		cx int
		id titleButton
	}
	btns := []btnSpec{
		{btnFirst + 0*btnStep, tbClose},
		{btnFirst + 1*btnStep, tbAbove},
		{btnFirst + 2*btnStep, tbMinimize},
	}
	for _, b := range btns {
		dx := ex - b.cx
		dy := ey - btnY
		if dx*dx+dy*dy <= btnHit*btnHit {
			return b.id
		}
	}
	return tbDragArea
}

// ── Event handling ────────────────────────────────────────────────────────────

// handleTitlebarButtonPress processes a ButtonPress event on a titlebar window.
func (wm *WM) handleTitlebarButtonPress(e xproto.ButtonPressEvent, c *Client) {
	// Focus the underlying client first.
	if c != wm.SelMon.Sel {
		wm.Focus(c)
		wm.Restack(wm.SelMon)
	}

	// Only handle button 1 (left click).
	if e.Detail != xproto.ButtonIndex1 {
		return
	}

	btn := hitTestTitlebar(int(e.EventX), int(e.EventY))
	switch btn {
	case tbClose:
		wm.killClient(c)
	case tbAbove:
		wm.SetAbove(c, !c.IsAbove)
		wm.drawTitlebar(c)
	case tbMinimize:
		wm.Minimize(nil)
	case tbDragArea:
		wm.titlebarDrag(c, e.RootX, e.RootY)
	}
}

// killClient kills the given client (used from titlebar without SelMon.Sel dependency).
func (wm *WM) killClient(c *Client) {
	if c == nil {
		return
	}
	if !wm.sendEvent(c, wm.WMAtom[WMDelete]) {
		xproto.KillClient(wm.Conn, uint32(c.Win))
	}
}

// titlebarDrag implements window movement by dragging the titlebar.
func (wm *WM) titlebarDrag(c *Client, startRootX, startRootY int16) {
	if c.IsFullscreen {
		return
	}

	ocx := c.X
	ocy := c.Y

	// GrabPointer to track mouse movement across windows.
	wm.Conn.Sync()
	reply, err := xproto.GrabPointer(wm.Conn, false, wm.Root,
		xproto.EventMaskButtonPress|xproto.EventMaskButtonRelease|xproto.EventMaskPointerMotion,
		xproto.GrabModeAsync, xproto.GrabModeAsync,
		xproto.WindowNone, wm.Cursors[CurMove], xproto.TimeCurrentTime).Reply()
	if err != nil || reply.Status != xproto.GrabStatusSuccess {
		return
	}

	ptrX := int(startRootX)
	ptrY := int(startRootY)

	for {
		ev := wm.nextDragEvent()
		if ev == nil {
			break
		}
		switch e := ev.(type) {
		case xproto.ConfigureRequestEvent:
			wm.handleConfigureRequest(e)
		case xproto.MapRequestEvent:
			wm.handleMapRequest(e)
		case xproto.MotionNotifyEvent:
			// Coalesce intermediate motion events.
			for {
				extra := wm.pollDragEvent()
				if extra == nil {
					break
				}
				if me, ok := extra.(xproto.MotionNotifyEvent); ok {
					e = me
				} else if _, ok := extra.(xproto.ButtonReleaseEvent); ok {
					goto done
				} else {
					wm.pendingEvts = append(wm.pendingEvts, extra)
				}
			}

			nx := ocx + (int(e.RootX) - ptrX)
			ny := ocy + (int(e.RootY) - ptrY)
			nx = wm.snapX(nx, ocx, c.Width())
			ny = wm.snapY(ny, ocy, c.Height())

			if !c.IsFloating {
				c.IsFloating = true
				wm.Arrange(c.Mon)
			}
			wm.Resize(c, nx, ny, c.W, c.H, true)

		case xproto.ButtonReleaseEvent:
			goto done
		}
	}

done:
	xproto.UngrabPointer(wm.Conn, xproto.TimeCurrentTime)
	if m := wm.RectToMon(c.X, c.Y, c.W, c.H); m != wm.SelMon {
		wm.sendMon(c, m)
		wm.SelMon = m
		wm.Focus(nil)
	}
	wm.replayPendingEvts()
}
