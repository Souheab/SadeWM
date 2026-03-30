import QtQuick
import Quickshell.Io
import ".."
import "../services"

Row {
    spacing: 6

    Image {
        source: Theme.logoSource
        width: Theme.logoSize
        height: Theme.logoSize
        anchors.verticalCenter: parent.verticalCenter
        sourceSize.width: Theme.logoSize
        sourceSize.height: Theme.logoSize
    }

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: tagRow.width + Theme.containerPadding
        height: Theme.containerHeight
        radius: Theme.containerRadius
        color: Theme.containerBg

        Row {
            id: tagRow
            anchors.centerIn: parent
            spacing: Theme.dotSpacing

            Repeater {
                model: Theme.tagCount

                Rectangle {
                    required property int index

                    width: (Theme.dotExpansion && isSelected) ? Theme.dotActiveWidth : Theme.dotSize
                    height: Theme.dotSize
                    radius: Theme.dotSize / 2
                    anchors.verticalCenter: parent.verticalCenter

                    Behavior on width {
                        enabled: Theme.dotExpansion
                        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                    }

                    property int tagNum: index + 1
                    property bool isUrgent:   TagService.urgent.indexOf(tagNum)   !== -1
                    property bool isSelected: TagService.selected.indexOf(tagNum) !== -1
                    property bool isOccupied: TagService.occupied.indexOf(tagNum) !== -1

                    color: {
                        if (isUrgent)   return dotArea.containsMouse ? Qt.darker(Theme.dotUrgent,   1.25) : Theme.dotUrgent
                        if (isSelected) return dotArea.containsMouse ? Qt.darker(Theme.dotSelected, 1.25) : Theme.dotSelected
                        if (isOccupied) return dotArea.containsMouse ? Qt.darker(Theme.dotOccupied, 1.25) : Theme.dotOccupied
                        return dotArea.containsMouse ? Qt.darker(Theme.dotEmpty, 1.4) : Theme.dotEmpty
                    }

                    MouseArea {
                        id: dotArea
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: Qt.PointingHandCursor

                        onClicked: mouse => {
                            if (mouse.button === Qt.LeftButton) {
                                tagCmd.command = ["python3", Qt.resolvedUrl("../scripts/qsctrl").toString().replace("file://", ""), "tags", "view", tagNum.toString()]
                            } else {
                                tagCmd.command = ["python3", Qt.resolvedUrl("../scripts/qsctrl").toString().replace("file://", ""), "tags", "toggle", tagNum.toString()]
                            }
                            tagCmd.running = true
                        }
                    }

                    Process {
                        id: tagCmd
                    }
                }
            }
        }
    }
}
