pragma Singleton

import Quickshell
import QtQuick

Singleton {
    // ── Bar ──
    readonly property int barHeight: 38
    readonly property color barBg: "#1a1b26"
    readonly property color containerBg: "#24283b"
    readonly property int containerRadius: 6
    readonly property int containerHeight: 22
    readonly property int containerPadding: 16
    readonly property int edgeMargin: 8

    // ── Colors ──
    readonly property color textColor: "#d8dee9"
    readonly property color dotUrgent: '#ff0019'
    readonly property color dotSelected: "#009fff"
    readonly property color dotOccupied: "#5e72cc"
    readonly property color dotEmpty: "#5c6a93"

    // ── Font ──
    readonly property string clockFont: "Lexend Deca"
    readonly property int clockFontSize: 12
    readonly property int textFontSize: 12
    readonly property string clockFormat: "dddd, d'th of' MMMM yyyy, hh:mm AP"

    // ── Dots ──
    readonly property int dotSize: 10
    readonly property int dotSpacing: 8
    readonly property int tagCount: 9

    // ── Logo ──
    readonly property int logoSize: 18
    readonly property string logoSource: Qt.resolvedUrl("assets/nixos-logo.svg")

    // ── Polling intervals (ms) ──
    readonly property int tagPollInterval: 100
    readonly property int volumePollInterval: 2000

    // ── Power Menu ──
    readonly property color menuBg: "#24283b"
    readonly property color menuHover: "#414868"
    readonly property color menuBorder: "#3b4252"
    readonly property int menuWidth: 200
    readonly property int menuItemHeight: 36
    readonly property int menuRadius: 8
    readonly property color dangerColor: "#bf616a"
    readonly property color confirmBg: "#1a1b26"
}
