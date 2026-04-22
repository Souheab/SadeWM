pragma Singleton
import QtQuick 2.15

// Mirrors shell/src/components/shared/Theme.qml — the sadeshell
// "Tokyo Night" palette and spacing scale, so the greeter feels like
// a natural first frame of the desktop session.
QtObject {
    // ── Colors ──
    readonly property color background:   "#1a1b26"
    readonly property color containerBg:  "#292e42"
    readonly property color menuHover:    "#3b4166"
    readonly property color menuBorder:   "#3d4166"
    readonly property color buttonBg:     "#323851"
    readonly property color buttonHover:  "#3b4166"
    readonly property color textColor:    "#c0caf5"
    readonly property color textMuted:    "#7f85a3"
    readonly property color accent:       "#7aa2f7"
    readonly property color accentMuted:  "#414868"
    readonly property color danger:       "#f7768e"
    readonly property color success:      "#9ece6a"

    // ── Spacing scale ──
    readonly property int spacingXS: 4
    readonly property int spacingSM: 8
    readonly property int spacingMD: 12
    readonly property int spacingLG: 16
    readonly property int spacingXL: 24

    // ── Radii & sizes ──
    readonly property int cardRadius:      20
    readonly property int containerRadius: 14
    readonly property int pillRadius:      999
    readonly property int cardWidth:       420
    readonly property int inputHeight:     44

    // ── Typography ──
    readonly property string uiFont:    "Lexend Deca"
    readonly property string monoFont:  "JetBrains Mono"
    readonly property int    titleSize: 26
    readonly property int    bodySize:  14
    readonly property int    smallSize: 12

    // ── Animation ──
    readonly property int animFast: 150
    readonly property int animMed:  300
}
