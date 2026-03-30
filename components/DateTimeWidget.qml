import QtQuick
import Quickshell
import ".."

Rectangle {
    id: dateTimeWidget
    width: timeText.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: dateArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool dateOpen: false
    property string timeStr: ""
    property string dateStr: ""

    property real popupX: 0
    property real popupY: 0

    readonly property Item popupLayer: {
        let p = parent;
        while (p) {
            for (let i = 0; i < p.children.length; i++) {
                if (p.children[i].objectName === "popupLayer")
                    return p.children[i];
            }
            p = p.parent;
        }
        return null;
    }

    function updatePopupPosition() {
        if (!popupLayer) return;
        const pos = dateTimeWidget.mapToItem(popupLayer, dateTimeWidget.width / 2, dateTimeWidget.height);
        popupX = pos.x - datePopup.width / 2;
        popupY = pos.y + 4;
    }

    onDateOpenChanged: if (popupLayer) popupLayer.popupVisible = dateOpen

    Connections {
        target: dateTimeWidget.popupLayer
        function onPopupVisibleChanged() {
            if (dateTimeWidget.popupLayer && !dateTimeWidget.popupLayer.popupVisible) {
                dateTimeWidget.dateOpen = false;
            }
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            const now = new Date();
            dateTimeWidget.timeStr = Qt.formatDateTime(now, Theme.timeFormat);
            dateTimeWidget.dateStr = Qt.formatDateTime(now, Theme.dateFormat);
        }
    }

    Text {
        id: timeText
        anchors.centerIn: parent
        text: dateTimeWidget.timeStr
        color: Theme.textColor
        font.pixelSize: Theme.textFontSize
        font.family: Theme.clockFont
    }

    MouseArea {
        id: dateArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
            if (dateTimeWidget.dateOpen) {
                dateTimeWidget.dateOpen = false;
            } else {
                dateTimeWidget.updatePopupPosition();
                dateTimeWidget.dateOpen = true;
            }
        }
    }

    Rectangle {
        id: datePopup
        parent: dateTimeWidget.popupLayer
        visible: dateTimeWidget.dateOpen
        x: dateTimeWidget.popupX
        y: dateTimeWidget.popupY
        width: dateText.width + 24
        height: dateText.height + 20
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        Text {
            id: dateText
            anchors.centerIn: parent
            text: dateTimeWidget.dateStr
            color: Theme.textColor
            font.pixelSize: Theme.textFontSize
            font.family: Theme.clockFont
        }
    }
}
