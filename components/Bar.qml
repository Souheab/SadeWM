import Quickshell
import QtQuick
import ".."
import "../services"

PanelWindow {
    anchors {
        top: true
        left: true
        right: true
    }
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

        // Center section - Date and time
        Item {
            width: parent.width * 0.34
            height: parent.height

            Clock {
                anchors.centerIn: parent
            }
        }

        // Right section - Volume
        Item {
            width: parent.width * 0.33
            height: parent.height

            VolumeWidget {
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                anchors.rightMargin: Theme.edgeMargin
            }
        }
    }
}
