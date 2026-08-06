package wm

import (
	"fmt"

	"github.com/jezek/xgb"
	"github.com/jezek/xgb/xproto"
)

// AtomName gives compile-time names to the ICCCM/EWMH atoms used by sadewm.
// Keeping the registry keyed by names, rather than parallel integer arrays,
// makes it impossible for enum ordering to silently advertise the wrong atom.
type AtomName string

type AtomRegistry map[AtomName]xproto.Atom

func (r AtomRegistry) Get(name AtomName) xproto.Atom { return r[name] }

const (
	UTF8String        AtomName = "UTF8_STRING"
	Manager           AtomName = "MANAGER"
	WMProtocols       AtomName = "WM_PROTOCOLS"
	WMDelete          AtomName = "WM_DELETE_WINDOW"
	WMState           AtomName = "WM_STATE"
	WMTakeFocus       AtomName = "WM_TAKE_FOCUS"
	WMChangeState     AtomName = "WM_CHANGE_STATE"
	WMColormapWindows AtomName = "WM_COLORMAP_WINDOWS"

	NetSupported          AtomName = "_NET_SUPPORTED"
	NetClientList         AtomName = "_NET_CLIENT_LIST"
	NetClientListStacking AtomName = "_NET_CLIENT_LIST_STACKING"
	NetNumberOfDesktops   AtomName = "_NET_NUMBER_OF_DESKTOPS"
	NetDesktopGeometry    AtomName = "_NET_DESKTOP_GEOMETRY"
	NetDesktopViewport    AtomName = "_NET_DESKTOP_VIEWPORT"
	NetCurrentDesktop     AtomName = "_NET_CURRENT_DESKTOP"
	NetDesktopNames       AtomName = "_NET_DESKTOP_NAMES"
	NetActiveWindow       AtomName = "_NET_ACTIVE_WINDOW"
	NetWorkarea           AtomName = "_NET_WORKAREA"
	NetWMCheck            AtomName = "_NET_SUPPORTING_WM_CHECK"
	NetShowingDesktop     AtomName = "_NET_SHOWING_DESKTOP"

	NetCloseWindow         AtomName = "_NET_CLOSE_WINDOW"
	NetMoveResizeWindow    AtomName = "_NET_MOVERESIZE_WINDOW"
	NetWMMoveResize        AtomName = "_NET_WM_MOVERESIZE"
	NetRestackWindow       AtomName = "_NET_RESTACK_WINDOW"
	NetRequestFrameExtents AtomName = "_NET_REQUEST_FRAME_EXTENTS"

	NetWMName                   AtomName = "_NET_WM_NAME"
	NetWMDesktop                AtomName = "_NET_WM_DESKTOP"
	NetWMWindowType             AtomName = "_NET_WM_WINDOW_TYPE"
	NetWMWindowTypeDesktop      AtomName = "_NET_WM_WINDOW_TYPE_DESKTOP"
	NetWMWindowTypeDock         AtomName = "_NET_WM_WINDOW_TYPE_DOCK"
	NetWMWindowTypeToolbar      AtomName = "_NET_WM_WINDOW_TYPE_TOOLBAR"
	NetWMWindowTypeMenu         AtomName = "_NET_WM_WINDOW_TYPE_MENU"
	NetWMWindowTypeUtility      AtomName = "_NET_WM_WINDOW_TYPE_UTILITY"
	NetWMWindowTypeSplash       AtomName = "_NET_WM_WINDOW_TYPE_SPLASH"
	NetWMWindowTypeDialog       AtomName = "_NET_WM_WINDOW_TYPE_DIALOG"
	NetWMWindowTypeDropdownMenu AtomName = "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU"
	NetWMWindowTypePopupMenu    AtomName = "_NET_WM_WINDOW_TYPE_POPUP_MENU"
	NetWMWindowTypeTooltip      AtomName = "_NET_WM_WINDOW_TYPE_TOOLTIP"
	NetWMWindowTypeNotification AtomName = "_NET_WM_WINDOW_TYPE_NOTIFICATION"
	NetWMWindowTypeCombo        AtomName = "_NET_WM_WINDOW_TYPE_COMBO"
	NetWMWindowTypeDND          AtomName = "_NET_WM_WINDOW_TYPE_DND"
	NetWMWindowTypeNormal       AtomName = "_NET_WM_WINDOW_TYPE_NORMAL"

	NetWMState                 AtomName = "_NET_WM_STATE"
	NetWMStateModal            AtomName = "_NET_WM_STATE_MODAL"
	NetWMStateSticky           AtomName = "_NET_WM_STATE_STICKY"
	NetWMStateMaximizedVert    AtomName = "_NET_WM_STATE_MAXIMIZED_VERT"
	NetWMStateMaximizedHorz    AtomName = "_NET_WM_STATE_MAXIMIZED_HORZ"
	NetWMStateShaded           AtomName = "_NET_WM_STATE_SHADED"
	NetWMStateSkipTaskbar      AtomName = "_NET_WM_STATE_SKIP_TASKBAR"
	NetWMStateSkipPager        AtomName = "_NET_WM_STATE_SKIP_PAGER"
	NetWMStateHidden           AtomName = "_NET_WM_STATE_HIDDEN"
	NetWMFullscreen            AtomName = "_NET_WM_STATE_FULLSCREEN"
	NetWMStateAbove            AtomName = "_NET_WM_STATE_ABOVE"
	NetWMStateBelow            AtomName = "_NET_WM_STATE_BELOW"
	NetWMStateDemandsAttention AtomName = "_NET_WM_STATE_DEMANDS_ATTENTION"
	NetWMStateFocused          AtomName = "_NET_WM_STATE_FOCUSED"
	// Obsolete compatibility alias. It is interned and accepted, not advertised.
	NetWMStateStaysOnTop AtomName = "_NET_WM_STATE_STAYS_ON_TOP"

	NetWMAllowedActions      AtomName = "_NET_WM_ALLOWED_ACTIONS"
	NetWMActionMove          AtomName = "_NET_WM_ACTION_MOVE"
	NetWMActionResize        AtomName = "_NET_WM_ACTION_RESIZE"
	NetWMActionMinimize      AtomName = "_NET_WM_ACTION_MINIMIZE"
	NetWMActionShade         AtomName = "_NET_WM_ACTION_SHADE"
	NetWMActionStick         AtomName = "_NET_WM_ACTION_STICK"
	NetWMActionMaximizeHorz  AtomName = "_NET_WM_ACTION_MAXIMIZE_HORZ"
	NetWMActionMaximizeVert  AtomName = "_NET_WM_ACTION_MAXIMIZE_VERT"
	NetWMActionFullscreen    AtomName = "_NET_WM_ACTION_FULLSCREEN"
	NetWMActionChangeDesktop AtomName = "_NET_WM_ACTION_CHANGE_DESKTOP"
	NetWMActionClose         AtomName = "_NET_WM_ACTION_CLOSE"
	NetWMActionAbove         AtomName = "_NET_WM_ACTION_ABOVE"
	NetWMActionBelow         AtomName = "_NET_WM_ACTION_BELOW"

	NetWMStrut              AtomName = "_NET_WM_STRUT"
	NetWMStrutPartial       AtomName = "_NET_WM_STRUT_PARTIAL"
	NetWMUserTime           AtomName = "_NET_WM_USER_TIME"
	NetWMUserTimeWindow     AtomName = "_NET_WM_USER_TIME_WINDOW"
	NetFrameExtents         AtomName = "_NET_FRAME_EXTENTS"
	NetWMWindowOpacity      AtomName = "_NET_WM_WINDOW_OPACITY"
	NetWMPing               AtomName = "_NET_WM_PING"
	NetWMSyncRequest        AtomName = "_NET_WM_SYNC_REQUEST"
	NetWMSyncRequestCounter AtomName = "_NET_WM_SYNC_REQUEST_COUNTER"
	NetWMFullscreenMonitors AtomName = "_NET_WM_FULLSCREEN_MONITORS"
	NetWMFullPlacement      AtomName = "_NET_WM_FULL_PLACEMENT"
)

var atomNames = []AtomName{
	UTF8String, Manager, WMProtocols, WMDelete, WMState, WMTakeFocus, WMChangeState, WMColormapWindows,
	NetSupported, NetClientList, NetClientListStacking, NetNumberOfDesktops,
	NetDesktopGeometry, NetDesktopViewport, NetCurrentDesktop, NetDesktopNames,
	NetActiveWindow, NetWorkarea, NetWMCheck, NetShowingDesktop,
	NetCloseWindow, NetMoveResizeWindow, NetWMMoveResize, NetRestackWindow,
	NetRequestFrameExtents, NetWMName, NetWMDesktop, NetWMWindowType,
	NetWMWindowTypeDesktop, NetWMWindowTypeDock, NetWMWindowTypeToolbar,
	NetWMWindowTypeMenu, NetWMWindowTypeUtility, NetWMWindowTypeSplash,
	NetWMWindowTypeDialog, NetWMWindowTypeDropdownMenu, NetWMWindowTypePopupMenu,
	NetWMWindowTypeTooltip, NetWMWindowTypeNotification, NetWMWindowTypeCombo,
	NetWMWindowTypeDND, NetWMWindowTypeNormal, NetWMState, NetWMStateModal,
	NetWMStateSticky, NetWMStateMaximizedVert, NetWMStateMaximizedHorz,
	NetWMStateShaded, NetWMStateSkipTaskbar, NetWMStateSkipPager,
	NetWMStateHidden, NetWMFullscreen, NetWMStateAbove, NetWMStateBelow,
	NetWMStateDemandsAttention, NetWMStateFocused, NetWMStateStaysOnTop,
	NetWMAllowedActions, NetWMActionMove, NetWMActionResize, NetWMActionMinimize,
	NetWMActionShade, NetWMActionStick, NetWMActionMaximizeHorz,
	NetWMActionMaximizeVert, NetWMActionFullscreen, NetWMActionChangeDesktop,
	NetWMActionClose, NetWMActionAbove, NetWMActionBelow, NetWMStrut,
	NetWMStrutPartial, NetWMUserTime, NetWMUserTimeWindow, NetFrameExtents,
	NetWMWindowOpacity, NetWMPing, NetWMSyncRequest, NetWMSyncRequestCounter,
	NetWMFullscreenMonitors, NetWMFullPlacement,
}

// supportedAtomNames is deliberately behavior-based. Conditional extension
// protocols (XSync and fullscreen monitor spanning) are appended at runtime.
var supportedAtomNames = []AtomName{
	NetSupported, NetClientList, NetClientListStacking, NetNumberOfDesktops,
	NetDesktopGeometry, NetDesktopViewport, NetCurrentDesktop, NetDesktopNames,
	NetActiveWindow, NetWorkarea, NetWMCheck, NetShowingDesktop,
	NetCloseWindow, NetMoveResizeWindow, NetWMMoveResize, NetRestackWindow,
	NetRequestFrameExtents, NetWMName, NetWMDesktop, NetWMWindowType,
	NetWMWindowTypeDesktop, NetWMWindowTypeDock, NetWMWindowTypeToolbar,
	NetWMWindowTypeMenu, NetWMWindowTypeUtility, NetWMWindowTypeSplash,
	NetWMWindowTypeDialog, NetWMWindowTypeDropdownMenu, NetWMWindowTypePopupMenu,
	NetWMWindowTypeTooltip, NetWMWindowTypeNotification, NetWMWindowTypeCombo,
	NetWMWindowTypeDND, NetWMWindowTypeNormal, NetWMState, NetWMStateModal,
	NetWMStateSticky, NetWMStateMaximizedVert, NetWMStateMaximizedHorz,
	NetWMStateShaded, NetWMStateSkipTaskbar, NetWMStateSkipPager,
	NetWMStateHidden, NetWMFullscreen, NetWMStateAbove, NetWMStateBelow,
	NetWMStateDemandsAttention, NetWMStateFocused, NetWMAllowedActions,
	NetWMActionMove, NetWMActionResize, NetWMActionMinimize, NetWMActionShade,
	NetWMActionStick, NetWMActionMaximizeHorz, NetWMActionMaximizeVert,
	NetWMActionFullscreen, NetWMActionChangeDesktop, NetWMActionClose,
	NetWMActionAbove, NetWMActionBelow, NetWMStrut, NetWMStrutPartial,
	NetWMUserTime, NetWMUserTimeWindow, NetFrameExtents,
	NetWMPing, NetWMFullPlacement,
}

func internAtomRegistry(conn *xgb.Conn) (AtomRegistry, error) {
	r := make(AtomRegistry, len(atomNames))
	for _, name := range atomNames {
		s := string(name)
		reply, err := xproto.InternAtom(conn, false, uint16(len(s)), s).Reply()
		if err != nil {
			return nil, fmt.Errorf("intern %s: %w", s, err)
		}
		r[name] = reply.Atom
	}
	return r, nil
}
