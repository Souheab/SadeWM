import QtQuick
import PyShell.Services 1.0
import "../shared"

Rectangle {
    id: notificationBtn
    width: Theme.containerHeight
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: btnArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool panelOpen: false

    readonly property Item popupLayer: {
        let p = parent
        while (p) {
            for (let i = 0; i < p.children.length; i++) {
                if (p.children[i].objectName === "popupLayer")
                    return p.children[i]
            }
            p = p.parent
        }
        return null
    }

    onPanelOpenChanged: if (popupLayer) popupLayer.popupVisible = panelOpen

    Connections {
        target: notificationBtn.popupLayer
        function onPopupVisibleChanged() {
            if (notificationBtn.popupLayer && !notificationBtn.popupLayer.popupVisible)
                notificationBtn.panelOpen = false
        }
    }

    Text {
        anchors.centerIn: parent
        text: "\uf0f3"
        color: btnArea.containsMouse ? Theme.textColor : Qt.alpha(Theme.textColor, 0.8)
        font.family: Theme.iconFont
        font.pixelSize: Theme.iconFontSize
    }

    MouseArea {
        id: btnArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: notificationBtn.panelOpen = !notificationBtn.panelOpen
    }

    NotificationPanel {
        popupLayer: notificationBtn.popupLayer
        panelOpen: notificationBtn.panelOpen
        onCloseRequested: notificationBtn.panelOpen = false
    }
}
