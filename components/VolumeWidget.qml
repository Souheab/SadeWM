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
            text: "🔊"
            font.pixelSize: 14
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: VolumeService.volume
            color: Theme.textColor
            font.pixelSize: Theme.textFontSize
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
