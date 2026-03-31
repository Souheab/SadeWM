pragma Singleton

import Quickshell
import QtQuick

Singleton {
    // ── Bar ──
    readonly property int barHeight: 40 
    readonly property color barBg: "#1a1b26"
    readonly property color containerBg: "#292e42"
    readonly property int containerRadius: 14
    readonly property int containerHeight: 28
    readonly property int containerPadding: 20
    readonly property int edgeMargin: 12

    // ── Spacing scale ──
    readonly property int spacingXS: 4
    readonly property int spacingSM: 8
    readonly property int spacingMD: 12
    readonly property int spacingLG: 16
    readonly property int spacingXL: 24

    // ── Colors ──
    readonly property color textColor: "#c0caf5"
    readonly property color dotUrgent: "#f7768e"
    // readonly property color dotSelected: "#2ac3de"
    readonly property color dotSelected: "#7aa2f7"
    readonly property color dotOccupied: "#666f99"
    readonly property color dotEmpty: "#414868"

    // ── Font ──
    readonly property string clockFont: "Lexend Deca"
    readonly property string monoFont: "JetBrains Mono"
    readonly property string iconFont: "FiraCode Nerd Font"
    readonly property int clockFontSize: 12
    readonly property int textFontSize: 13
    readonly property int iconFontSize: 16
    readonly property string clockFormat: "dddd, d'th of' MMMM yyyy, hh:mm AP"
    readonly property string timeFormat: "hh:mm AP"
    readonly property string dateFormat: "dddd, d'th of' MMMM yyyy"

    // ── Dots ──
    readonly property int dotSize: 8
    readonly property int dotActiveWidth: 24
    readonly property int dotSpacing: 6
    readonly property int tagCount: 9
    readonly property bool dotExpansion: true

    // ── Logo ──
    readonly property int logoSize: 18
    readonly property string logoSource: Qt.resolvedUrl("assets/nixos-logo.svg")

    // ── Polling intervals (ms) ──
    readonly property int tagPollInterval: 100
    readonly property int volumePollInterval: 2000

    // ── Power Menu ──
    readonly property color menuBg: "#292e42"
    readonly property color menuHover: "#3b4166"
    readonly property color menuBorder: "#3d4166"
    readonly property int menuWidth: 200
    readonly property int menuItemHeight: 40
    readonly property int menuRadius: 12
    readonly property color dangerColor: "#bf616a"
    readonly property color confirmBg: "#1a1b26"

    // ── Popup dimensions ──
    readonly property int sidebarWidth: 320
    readonly property int calendarWidth: 300
    readonly property int confirmDialogWidth: 280
    readonly property int sectionHeaderHeight: 40
    readonly property int wifiTogglePillWidth: 48
    readonly property int launcherWidth: 340
    readonly property int launcherMaxHeight: 480
    readonly property int launcherItemHeight: 52

    // ── Animation ──
    readonly property int popupAnimDuration: 500
    readonly property int popupAnimEasing: Easing.OutQuart
}
