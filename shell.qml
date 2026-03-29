import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    PanelWindow {
        id: panel

        // ── Theme ──
        readonly property int barHeight: 38
        readonly property color barBg: "#1a1b26"
        readonly property color containerBg: "#24283b"
        readonly property int containerRadius: 6
        readonly property int containerHeight: 22
        readonly property int containerPadding: 16
        readonly property int edgeMargin: 8

        // ── Colors ──
        readonly property color textColor: "#d8dee9"
        readonly property color dotUrgent: "#bf616a"
        readonly property color dotSelected: "#88c0d0"
        readonly property color dotOccupied: "#81a1c1"
        readonly property color dotEmpty: "#3b4252"

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
        readonly property string logoSource: "assets/nixos-logo.svg"

        // ── Polling intervals (ms) ──
        readonly property int tagPollInterval: 100
        readonly property int volumePollInterval: 2000

        anchors {
            top: true
            left: true
            right: true
        }
        height: barHeight
        color: barBg

        property var selectedTags: []
        property var occupiedTags: []
        property var urgentTags: []
        property string volumeText: "100%"

        property string clockText: Qt.formatDateTime(new Date(), panel.clockFormat)

        Timer {
            interval: 1000
            running: true
            repeat: true
            onTriggered: panel.clockText = Qt.formatDateTime(new Date(), panel.clockFormat)
        }

        Process {
            id: tagProcess
            command: ["bash", "-c", "echo 'local sel,occ,urg=\"\",\"\",\"\"; for _,t in ipairs(require(\"awful\").screen.focused().tags) do if t.selected then sel=sel..t.name end; if #t:clients()>0 then occ=occ..t.name end; if t.urgent then urg=urg..t.name end end; return sel..\"|\"..occ..\"|\"..urg' | awesome-client"]

            stdout: SplitParser {
                onRead: data => {
                    var match = data.match(/string "([^"]*)"/);
                    if (match && match[1]) {
                        var parts = match[1].split("|");
                        panel.selectedTags = parts[0].split("").map(function(t) { return parseInt(t) });
                        panel.occupiedTags = parts[1] ? parts[1].split("").map(function(t) { return parseInt(t) }) : [];
                        panel.urgentTags = parts[2] ? parts[2].split("").map(function(t) { return parseInt(t) }) : [];
                    }
                }
            }
        }

        Timer {
            interval: panel.tagPollInterval
            running: true
            repeat: true
            onTriggered: tagProcess.running = true
        }

        Process {
            id: volumeProcess
            command: ["bash", "-c", "pamixer --get-volume"]

            stdout: SplitParser {
                onRead: data => {
                    var vol = data.trim()
                    if (vol.length > 0) {
                        panel.volumeText = vol + "%"
                    }
                }
            }
        }

        Timer {
            interval: panel.volumePollInterval
            running: true
            repeat: true
            onTriggered: volumeProcess.running = true
        }

        Row {
            anchors.fill: parent
            spacing: 0

            // Left section - Workspace dots
            Item {
                width: parent.width * 0.33
                height: parent.height

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    x: panel.edgeMargin
                    spacing: 6

                    Image {
                        source: panel.logoSource
                        width: panel.logoSize
                        height: panel.logoSize
                        anchors.verticalCenter: parent.verticalCenter
                        sourceSize.width: panel.logoSize
                        sourceSize.height: panel.logoSize
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: tagRow.width + panel.containerPadding
                        height: panel.containerHeight
                        radius: panel.containerRadius
                        color: panel.containerBg

                        Row {
                            id: tagRow
                            anchors.centerIn: parent
                            spacing: panel.dotSpacing

                            Repeater {
                                model: panel.tagCount

                                Rectangle {
                                    required property int index
                                    width: panel.dotSize
                                    height: panel.dotSize
                                    radius: panel.dotSize / 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: {
                                        var tagNum = index + 1
                                        if (panel.urgentTags.indexOf(tagNum) !== -1) {
                                            return panel.dotUrgent
                                        }
                                        if (panel.selectedTags.indexOf(tagNum) !== -1) {
                                            return panel.dotSelected
                                        }
                                        if (panel.occupiedTags.indexOf(tagNum) !== -1) {
                                            return panel.dotOccupied
                                        }
                                        return panel.dotEmpty
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Center section - Date and time
            Item {
                width: parent.width * 0.34
                height: parent.height

                Text {
                    anchors.centerIn: parent
                    text: panel.clockText
                    color: panel.textColor
                    font.pixelSize: panel.clockFontSize
                    font.family: panel.clockFont
                }
            }

            // Right section - Volume
            Item {
                width: parent.width * 0.33
                height: parent.height

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: panel.edgeMargin
                    width: volumeRow.width + panel.containerPadding
                    height: panel.containerHeight
                    radius: panel.containerRadius
                    color: panel.containerBg

                    Row {
                        id: volumeRow
                        anchors.centerIn: parent
                        spacing: 4

                        Text {
                            text: "🔊"
                            font.pixelSize: 14
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: panel.volumeText
                            color: panel.textColor
                            font.pixelSize: panel.textFontSize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }
    }
}
