import QtQuick
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
                    color: {
                        var tagNum = index + 1
                        if (TagService.urgent.indexOf(tagNum) !== -1) {
                            return Theme.dotUrgent
                        }
                        if (TagService.selected.indexOf(tagNum) !== -1) {
                            return Theme.dotSelected
                        }
                        if (TagService.occupied.indexOf(tagNum) !== -1) {
                            return Theme.dotOccupied
                        }
                        return Theme.dotEmpty
                    }
                }
            }
        }
    }
}
