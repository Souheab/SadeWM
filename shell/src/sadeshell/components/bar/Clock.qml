import QtQuick
import "../shared"

Text {
    property string clockText: Qt.formatDateTime(new Date(), Theme.clockFormat)

    text: clockText
    color: Theme.textColor
    font.family: Theme.monoFont
    font.pixelSize: Theme.clockFontSize

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: parent.clockText = Qt.formatDateTime(new Date(), Theme.clockFormat)
    }
}
