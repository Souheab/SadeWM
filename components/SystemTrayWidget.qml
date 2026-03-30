import QtQuick
import Quickshell
import Quickshell.Services.SystemTray
import Quickshell.Widgets
import ".."

Rectangle {
    // Must be set to the enclosing PanelWindow (pass `root` from Bar.qml)
    property var shellWindow: null

    visible: trayRepeater.count > 0
    implicitWidth: trayRepeater.count > 0
        ? trayRepeater.count * Theme.containerHeight + (trayRepeater.count - 1) * 2 + Theme.containerPadding
        : 0
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg

    Row {
        id: trayRow
        anchors.centerIn: parent
        spacing: 2

        Repeater {
            id: trayRepeater
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
                    source: modelData.icon
                    mipmap: true
                }

                MouseArea {
                    id: iconArea
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: mouse => {
                        if (mouse.button === Qt.RightButton || modelData.onlyMenu) {
                            const pos = iconArea.mapToItem(null, mouse.x, mouse.y);
                            modelData.display(shellWindow, pos.x, pos.y);
                        } else {
                            modelData.activate();
                        }
                    }
                }
            }
        }
    }
}
