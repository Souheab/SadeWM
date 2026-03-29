import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    PanelWindow {
        id: panel

        anchors {
            top: true
            left: true
            right: true
        }
        height: 28
        color: "#1a1b26"

        property var selectedTags: []
        property var occupiedTags: []
        property var urgentTags: []
        property string volumeText: "100%"

        property string clockText: Qt.formatDateTime(new Date(), "dddd, d'th of' MMMM yyyy, hh:mm AP")

        Timer {
            interval: 1000
            running: true
            repeat: true
            onTriggered: panel.clockText = Qt.formatDateTime(new Date(), "dddd, d'th of' MMMM yyyy, hh:mm AP")
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
            interval: 100
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
            interval: 2000
            running: true
            repeat: true
            onTriggered: volumeProcess.running = true
        }

        Row {
            anchors.fill: parent
            spacing: 0

            // Left section - Workspace dots
            Row {
                width: parent.width * 0.33
                height: parent.height
                spacing: 8
                leftPadding: 12

                Repeater {
                    model: 9

                    Rectangle {
                        required property int index
                        width: 10
                        height: 10
                        radius: 5
                        anchors.verticalCenter: parent.verticalCenter
                        color: {
                            var tagNum = index + 1
                            if (panel.urgentTags.indexOf(tagNum) !== -1) {
                                return "#bf616a"  // red - urgent
                            }
                            if (panel.selectedTags.indexOf(tagNum) !== -1) {
                                return "#88c0d0"  // cyan blue - selected
                            }
                            if (panel.occupiedTags.indexOf(tagNum) !== -1) {
                                return "#81a1c1"  // light grayish blue - occupied
                            }
                            return "#3b4252"    // dark - empty
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
                    color: "#d8dee9"
                    font.pixelSize: 12
                    font.family: "sans-serif"
                }
            }

            // Right section - Volume
            Row {
                width: parent.width * 0.33
                height: parent.height
                layoutDirection: Qt.RightToLeft
                rightPadding: 12
                spacing: 4

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    Text {
                        text: "🔊"
                        font.pixelSize: 14
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        text: panel.volumeText
                        color: "#d8dee9"
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }
    }
}
