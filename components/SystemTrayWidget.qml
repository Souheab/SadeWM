import QtQuick
import Quickshell
import Quickshell.Services.SystemTray
import Quickshell.Widgets
import ".."

Row {
    spacing: 2
    height: Theme.containerHeight

    Repeater {
        model: SystemTray.items

        delegate: Rectangle {
            required property var modelData

            implicitWidth: Theme.containerHeight
            implicitHeight: Theme.containerHeight
            radius: Theme.containerRadius
            color: iconArea.containsMouse ? Theme.menuHover : "transparent"

            IconImage {
                anchors.centerIn: parent
                implicitSize: 16
                source: "image://icon/" + modelData.icon
                mipmap: true
            }

            MouseArea {
                id: iconArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: mouse => {
                    if (mouse.button === Qt.RightButton || modelData.onlyMenu) {
                        modelData.display(null, 0, 0);
                    } else {
                        modelData.activate();
                    }
                }
            }
        }
    }
}
