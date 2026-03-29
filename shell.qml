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
        height: 32
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
            Item {
                width: parent.width * 0.33
                height: parent.height

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    x: 8
                    spacing: 6

                    Image {
                        source: "assets/nixos-logo.svg"
                        width: 18
                        height: 18
                        anchors.verticalCenter: parent.verticalCenter
                        sourceSize.width: 18
                        sourceSize.height: 18
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: tagRow.width + 16
                        height: 22
                        radius: 6
                        color: "#24283b"

                        Row {
                            id: tagRow
                            anchors.centerIn: parent
                            spacing: 8

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
                                            return "#bf616a"
                                        }
                                        if (panel.selectedTags.indexOf(tagNum) !== -1) {
                                            return "#88c0d0"
                                        }
                                        if (panel.occupiedTags.indexOf(tagNum) !== -1) {
                                            return "#81a1c1"
                                        }
                                        return "#3b4252"
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
                    color: "#d8dee9"
                    font.pixelSize: 12
                    font.family: "Lexend Deca"
                }
            }

            // Right section - Volume
            Item {
                width: parent.width * 0.33
                height: parent.height

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    width: volumeRow.width + 16
                    height: 22
                    radius: 6
                    color: "#24283b"

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
                            color: "#d8dee9"
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }
    }
}
