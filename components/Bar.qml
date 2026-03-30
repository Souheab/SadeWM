import Quickshell
import QtQuick
import ".."
import "../services"

// Full-screen PanelWindow: the bar is a Rectangle at the top,
// and popup content (dropdowns, dialogs) renders below it as siblings.
// When no popup is open, the mask restricts input to the bar strip only,
// making the rest of the screen click-through.
PanelWindow {
    id: root

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    // Input mask: only the bar is interactive when no popup is open.
    // When a popup is open, the full window accepts input (for click-outside-to-close).
    mask: Region {
        x: 0
        y: 0
        width: root.width
        height: popupLayer.popupVisible ? root.height : Theme.barHeight
    }

    // Bar background at the top
    Rectangle {
        id: barArea
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.barHeight
        color: Theme.barBg

        Row {
            anchors.fill: parent
            spacing: 0

            // Left section - Workspace dots
            Item {
                width: parent.width * 0.33
                height: parent.height

                WorkspaceDots {
                    anchors.verticalCenter: parent.verticalCenter
                    x: Theme.edgeMargin
                }
            }

            // Center section
            Item {
                width: parent.width * 0.34
                height: parent.height
            }

            // Right section - Volume + Power
            Item {
                width: parent.width * 0.33
                height: parent.height

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.edgeMargin
                    spacing: 6
                    layoutDirection: Qt.RightToLeft

                    PowerMenu {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    SystemTrayWidget {
                        anchors.verticalCenter: parent.verticalCenter
                        shellWindow: root
                    }

                    VolumeWidget {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    DateTimeWidget {
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }
    }

    // Click-outside-to-close: covers the area below the bar
    MouseArea {
        anchors.top: barArea.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: popupLayer.popupVisible
        onClicked: popupLayer.popupVisible = false
    }

    // Popup layer: sits on top of everything.
    // PowerMenu (and future popup widgets) reparent their content here.
    Item {
        id: popupLayer
        objectName: "popupLayer"
        property bool popupVisible: false
        anchors.fill: parent
    }
}
