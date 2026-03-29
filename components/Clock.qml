import QtQuick
import ".."

Text {
    property string clockText: Qt.formatDateTime(new Date(), Theme.clockFormat)

    text: clockText
    color: Theme.textColor
    font.pixelSize: Theme.clockFontSize
    font.family: Theme.clockFont

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: parent.clockText = Qt.formatDateTime(new Date(), Theme.clockFormat)
    }
}
