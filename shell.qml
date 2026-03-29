import QtQuick
import Quickshell
import Quickshell.Widgets
import Quickshell.Io

PanelWindow {
    id: panel
    
    anchors {
        top: true
        left: true
        right: true
    }
    height: 28
    color: "#2e3440"
    
    property var selectedTags: []
    
    Process {
        id: tagProcess
        command: ["bash", "/home/suller/.config/quickshell/scripts/get_tags.sh"]
        
        onExited: {
            if (exitCode === 0) {
                var output = (stdout || "").trim()
                // Parse output like '   string "267"'
                var match = output.match(/string "([^"]*)"/)
                if (match && match[1]) {
                    var tags = match[1].split("").map(function(t) { return parseInt(t) })
                    panel.selectedTags = tags
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

    Row {
        anchors.fill: parent
        spacing: 0

        // Left section - Workspace indicators
        Row {
            width: parent.width * 0.33
            height: parent.height
            spacing: 8
            leftPadding: 12

            Repeater {
                model: 9
                
                Rectangle {
                    width: 10
                    height: 10
                    radius: 5
                    anchors.verticalCenter: parent.verticalCenter
                    color: {
                        var tagNum = index + 1
                        if (panel.selectedTags.indexOf(tagNum) !== -1) {
                            return "#5e81ac"  // Active workspace - blue
                        }
                        return "#3b4252"  // Inactive - darker gray
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
                text: Qt.formatDateTime(new Date(), "dddd, d'th' 'of' MMMM yyyy, hh:mm AP")
                color: "#d8dee9"
                font.pixelSize: 12
                font.family: "sans-serif"
            }
        }

        // Right section - System tray
        Row {
            width: parent.width * 0.33
            height: parent.height
            spacing: 12
            layoutDirection: Qt.RightToLeft
            rightPadding: 12

            // App grid icon
            Rectangle {
                width: 20
                height: 20
                anchors.verticalCenter: parent.verticalCenter
                color: "transparent"
                
                Grid {
                    anchors.centerIn: parent
                    columns: 3
                    rows: 3
                    spacing: 2
                    
                    Repeater {
                        model: 9
                        Rectangle {
                            width: 3
                            height: 3
                            color: "#d8dee9"
                        }
                    }
                }
            }

            // WiFi icon
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "📶"
                font.pixelSize: 14
            }

            // Volume with percentage
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                
                Text {
                    text: "100%"
                    color: "#d8dee9"
                    font.pixelSize: 12
                }
                
                Text {
                    text: "🔊"
                    font.pixelSize: 14
                }
            }
        }
    }
}
