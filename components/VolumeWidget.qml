import QtQuick
import ".."
import "../services"

Rectangle {
    width: volumeRow.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg

    Row {
        id: volumeRow
        anchors.centerIn: parent
        spacing: 4

        Text {
            text: "\uf028"
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            color: Theme.textColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: VolumeService.volume
            color: Theme.textColor
            font.family: Theme.monoFont
            font.pixelSize: Theme.textFontSize
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
