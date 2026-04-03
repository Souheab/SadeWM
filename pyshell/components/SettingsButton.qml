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
        onClicked: settingsBtn.panelOpen = !settingsBtn.panelOpen
    }

    SettingsPanel {
        popupLayer: settingsBtn.popupLayer
        panelOpen: settingsBtn.panelOpen
        onCloseRequested: settingsBtn.panelOpen = false
    }
}
