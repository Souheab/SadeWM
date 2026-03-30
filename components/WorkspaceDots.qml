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

                    width: Theme.dotSize
                    height: Theme.dotSize
                    radius: Theme.dotSize / 2
                    anchors.verticalCenter: parent.verticalCenter

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
                                // View tag (switch to it)
                                tagCmd.command = ["bash", "-c",
                                    "awesome-client 'local s=require(\"awful\").screen.focused(); for _,t in ipairs(s.tags) do if t.name==\"" + tagNum + "\" then t:view_only() end end'"]
                            } else {
                                // Toggle tag
                                tagCmd.command = ["bash", "-c",
                                    "awesome-client 'local s=require(\"awful\").screen.focused(); for _,t in ipairs(s.tags) do if t.name==\"" + tagNum + "\" then require(\"awful\").tag.viewtoggle(t) end end'"]
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
