import QtQuick
import PyShell.Services 1.0
import "../shared"

Rectangle {
    width: volumeRow.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg

    // Show volume of the default sink
    readonly property int currentVolume: {
        var sinks = AudioService.sinks;
        for (var i = 0; i < sinks.length; i++) {
            if (sinks[i].isDefault)
                return sinks[i].volume;
        }
        return 0;
    }

    readonly property bool currentMuted: {
        var sinks = AudioService.sinks;
        for (var i = 0; i < sinks.length; i++) {
            if (sinks[i].isDefault)
                return sinks[i].muted;
        }
        return false;
    }

    Row {
        id: volumeRow
        anchors.centerIn: parent
        spacing: 4

        Text {
            text: currentMuted ? "\uf6a9" : (currentVolume > 50 ? "\uf028" : "\uf027")
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            color: currentMuted ? Theme.dotEmpty : Theme.textColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: currentVolume
            color: currentMuted ? Theme.dotEmpty : Theme.textColor
            font.family: Theme.monoFont
            font.pixelSize: Theme.textFontSize
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
