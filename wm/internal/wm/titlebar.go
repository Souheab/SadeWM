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

// ── palette (from sadeshell Theme.qml) ────────────────────────────────────────
#define TB_BG_R   0.102
#define TB_BG_G   0.106
#define TB_BG_B   0.149   // #1a1b26

#define TB_BG_F_R 0.125
#define TB_BG_F_G 0.133
#define TB_BG_F_B 0.192   // slightly lighter when focused

#define TB_SEP_R  0.161
#define TB_SEP_G  0.180
#define TB_SEP_B  0.259   // #292e42

#define TB_TXT_R  0.753
#define TB_TXT_G  0.792
#define TB_TXT_B  0.961   // #c0caf5

// Button colours
#define TB_CLOSE_R  0.969
#define TB_CLOSE_G  0.463
#define TB_CLOSE_B  0.557  // #f7768e  close

#define TB_ABOVE_R  0.478
#define TB_ABOVE_G  0.635
#define TB_ABOVE_B  0.969  // #7aa2f7  stay-on-top (active)

#define TB_ABOVE_DIM 0.45  // alpha for follow-on-top when inactive

#define TB_MIN_R    0.400
#define TB_MIN_G    0.435
#define TB_MIN_B    0.600  // #666f99  minimize

// Button layout constants
#define TB_BTN_R       6.0   // button radius (px)
#define TB_BTN_FIRST_X 16    // centre-x of first button
#define TB_BTN_STEP    20    // x distance between button centres
#define TB_ROUND_RADIUS 6.0  // top-corner radius

// Open an Xlib display connection.  Returns NULL on failure.
static Display* tb_open_display(const char* name) {
    return XOpenDisplay(name);
}

// Non-fatal X error handler so that Cairo RENDER errors (e.g. freeing a
// picture for a destroyed window) do not kill the WM via exit(1).
static int tb_xerror_handler(Display *dpy, XErrorEvent *ev) {
    // Silently ignore; Cairo is resilient to these.
    (void)dpy; (void)ev;
    return 0;
}

static void tb_install_error_handler() {
    XSetErrorHandler(tb_xerror_handler);
}

// Apply a rounded-top-corner shape mask to the titlebar window.
// Must be called after mapping and after any width change.
static void tb_apply_rounded_shape(Display *dpy, Window win, int w, int h) {
    double r = TB_ROUND_RADIUS;
    Pixmap mask = XCreatePixmap(dpy, win, w, h, 1);
    if (!mask) return;
    Screen *screen = DefaultScreenOfDisplay(dpy);
    cairo_surface_t *ms = cairo_xlib_surface_create_for_bitmap(dpy, mask, screen, w, h);
    if (!ms) { XFreePixmap(dpy, mask); return; }
    cairo_t *cr = cairo_create(ms);
    if (!cr) { cairo_surface_destroy(ms); XFreePixmap(dpy, mask); return; }
    // Clear to 0 (transparent / clipped out)
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    // Draw rounded-top rect in 1 (opaque)
    cairo_set_source_rgba(cr, 1, 1, 1, 1);
    cairo_new_path(cr);
    cairo_arc(cr, r, r, r, M_PI, 3*M_PI/2);       // top-left
    cairo_arc(cr, w - r, r, r, -M_PI/2, 0);        // top-right
    cairo_line_to(cr, w, h);                         // bottom-right
    cairo_line_to(cr, 0, h);                         // bottom-left
    cairo_close_path(cr);
    cairo_fill(cr);
    cairo_destroy(cr);
    cairo_surface_finish(ms);
    cairo_surface_destroy(ms);
    XShapeCombineMask(dpy, win, ShapeBounding, 0, 0, mask, ShapeSet);
    XFreePixmap(dpy, mask);
    XFlush(dpy);
}

// Draw the titlebar into window |win| using Cairo Xlib surface.
//
// Parameters:
//   dpy       - Xlib Display *
//   win       - X11 Window id (the titlebar window)
//   w, h      - titlebar dimensions in pixels
//   title     - UTF-8 window title (may be NULL / empty)
//   focused   - non-zero when the associated client is focused
//   is_above  - non-zero when client has stay-on-top set
//   hover_btn - 1=close, 2=above, 3=minimize, 0=none
static void tb_draw(Display *dpy, unsigned long win,
                    int w, int h,
                    const char *title,
                    int focused, int is_above, int hover_btn) {
    Visual *visual = XDefaultVisual(dpy, DefaultScreen(dpy));
    cairo_surface_t *surface = cairo_xlib_surface_create(
        dpy, (Drawable)win, visual, w, h);
    if (!surface) return;

    cairo_t *cr = cairo_create(surface);
    if (!cr) {
        cairo_surface_destroy(surface);
        return;
    }

    // ── rounded background (top corners only) ────────────────────────────────
    if (focused) {
        cairo_set_source_rgb(cr, TB_BG_F_R, TB_BG_F_G, TB_BG_F_B);
    } else {
        cairo_set_source_rgb(cr, TB_BG_R, TB_BG_G, TB_BG_B);
    }
    {
        double r = TB_ROUND_RADIUS;
        cairo_new_path(cr);
        cairo_arc(cr, r, r, r, M_PI, 3*M_PI/2);
        cairo_arc(cr, w - r, r, r, -M_PI/2, 0);
        cairo_line_to(cr, w, h);
        cairo_line_to(cr, 0, h);
        cairo_close_path(cr);
        cairo_fill(cr);
    }

    // ── bottom separator ──────────────────────────────────────────────────────
    cairo_set_source_rgb(cr, TB_SEP_R, TB_SEP_G, TB_SEP_B);
    cairo_set_line_width(cr, 1.0);
    cairo_move_to(cr, 0, h - 0.5);
    cairo_line_to(cr, w, h - 0.5);
    cairo_stroke(cr);

    // ── buttons ───────────────────────────────────────────────────────────────
    double by = h / 2.0;

    // Close (red)
    double cx0 = TB_BTN_FIRST_X;
    cairo_arc(cr, cx0, by, TB_BTN_R, 0, 2 * M_PI);
    cairo_set_source_rgb(cr, TB_CLOSE_R, TB_CLOSE_G, TB_CLOSE_B);
    cairo_fill(cr);
    if (hover_btn == 1) {
        double ic = TB_BTN_R * 0.50;
        cairo_set_source_rgba(cr, 0.0, 0.0, 0.0, 0.75);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx0 - ic, by - ic); cairo_line_to(cr, cx0 + ic, by + ic); cairo_stroke(cr);
        cairo_move_to(cr, cx0 + ic, by - ic); cairo_line_to(cr, cx0 - ic, by + ic); cairo_stroke(cr);
    }

    // Stay-on-top (blue; dimmed when not active)
    double cx1 = TB_BTN_FIRST_X + TB_BTN_STEP;
    cairo_arc(cr, cx1, by, TB_BTN_R, 0, 2 * M_PI);
    if (is_above) {
        cairo_set_source_rgb(cr, TB_ABOVE_R, TB_ABOVE_G, TB_ABOVE_B);
    } else {
        cairo_set_source_rgba(cr, TB_ABOVE_R, TB_ABOVE_G, TB_ABOVE_B, TB_ABOVE_DIM);
    }
    cairo_fill(cr);
    if (hover_btn == 2) {
        double aw = TB_BTN_R * 0.55;
        double ah = TB_BTN_R * 0.50;
        cairo_set_source_rgba(cr, 0.0, 0.0, 0.0, 0.75);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx1 - aw, by + ah * 0.4);
        cairo_line_to(cr, cx1,       by - ah * 0.8);
        cairo_line_to(cr, cx1 + aw, by + ah * 0.4);
        cairo_stroke(cr);
    }

    // Minimize (muted purple-gray)
    double cx2 = TB_BTN_FIRST_X + 2 * TB_BTN_STEP;
    cairo_arc(cr, cx2, by, TB_BTN_R, 0, 2 * M_PI);
    cairo_set_source_rgb(cr, TB_MIN_R, TB_MIN_G, TB_MIN_B);
    cairo_fill(cr);
    if (hover_btn == 3) {
        double hw = TB_BTN_R * 0.55;
        cairo_set_source_rgba(cr, 0.0, 0.0, 0.0, 0.75);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, cx2 - hw, by); cairo_line_to(cr, cx2 + hw, by); cairo_stroke(cr);
    }

    // ── window title ──────────────────────────────────────────────────────────
    if (title && title[0] != '\0') {
        cairo_set_source_rgb(cr, TB_TXT_R, TB_TXT_G, TB_TXT_B);
        cairo_select_font_face(cr, "Sans",
            CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
        cairo_set_font_size(cr, 12.0);

        cairo_text_extents_t ext;
        cairo_text_extents(cr, title, &ext);

        // Center, keeping clear of the three buttons (left guard ~65 px)
        double max_w = (double)(w - 70 - 10);
        double tx;
        if (ext.width > max_w) {
            tx = 70;  // left-align if too long to center
        } else {
            tx = (w - ext.width) / 2.0 - ext.x_bearing;
            if (tx < 70) tx = 70;
        }
        double ty = (h - ext.height) / 2.0 - ext.y_bearing;

        cairo_move_to(cr, tx, ty);
        cairo_show_text(cr, title);
    }

    // ── flush ─────────────────────────────────────────────────────────────────
    cairo_surface_flush(surface);
    XFlush(dpy);

    cairo_destroy(cr);
    cairo_surface_destroy(surface);
}
*/
import "C"

import (
	"os"
	"unsafe"

	"github.com/BurntSushi/xgb/xproto"
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

	C.tb_draw(
		(*C.Display)(wm.XlibDpy),
		C.ulong(c.TitleWin),
		C.int(tbW),
		C.int(tbH),
		cTitle,
		boolToInt(focused),
		boolToInt(c.IsAbove),
		C.int(c.TitleHover),
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
