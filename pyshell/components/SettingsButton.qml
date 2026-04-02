import QtQuick
import PyShell.Services 1.0

Rectangle {
    id: settingsBtn
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
        target: settingsBtn.popupLayer
        function onPopupVisibleChanged() {
            if (settingsBtn.popupLayer && !settingsBtn.popupLayer.popupVisible)
                settingsBtn.panelOpen = false
        }
    }

    Rectangle {
        visible: NotificationService.unreadCount > 0
        width: 14
        height: 14
        radius: 7
        color: Theme.dotUrgent
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 1
        anchors.rightMargin: 1
        z: 1

        Text {
            anchors.centerIn: parent
            text: NotificationService.unreadCount > 9 ? "9+" : NotificationService.unreadCount.toString()
            color: "#1a1b26"
            font.family: Theme.monoFont
            font.pixelSize: 7
            font.bold: true
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
        onClicked: settingsBtn.panelOpen = !settingsBtn.panelOpen
    }

    SettingsPanel {
        popupLayer: settingsBtn.popupLayer
        panelOpen: settingsBtn.panelOpen
        onCloseRequested: settingsBtn.panelOpen = false
    }
}
