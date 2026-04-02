import QtQuick
import PyShell.Services 1.0

Rectangle {
    id: networkWidget

    implicitWidth: iconRow.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: barArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool sidebarOpen: false

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

    onSidebarOpenChanged: {
        if (popupLayer) popupLayer.popupVisible = sidebarOpen;
        if (sidebarOpen) WiFiService.scan();
    }

    Connections {
        target: networkWidget.popupLayer
        function onPopupVisibleChanged() {
            if (networkWidget.popupLayer && !networkWidget.popupLayer.popupVisible)
                networkWidget.sidebarOpen = false;
        }
    }

    Row {
        id: iconRow
        anchors.centerIn: parent
        spacing: 6

        Text {
            text: "\uf1eb"
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            anchors.verticalCenter: parent.verticalCenter
            color: {
                if (!WiFiService.wifiEnabled) return Theme.dotEmpty;
                if (!WiFiService.connectedSsid) return Theme.textColor;
                return WiFiService.connectedSignal >= 60 ? Theme.dotSelected : "#e0af68";
            }
        }
    }

    MouseArea {
        id: barArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: networkWidget.sidebarOpen = !networkWidget.sidebarOpen
    }

    // Sidebar panel
    Rectangle {
        id: sidebar
        parent: networkWidget.popupLayer
        visible: opacity > 0
        opacity: networkWidget.sidebarOpen ? 1.0 : 0.0
        x: networkWidget.popupLayer ? networkWidget.popupLayer.width - width - Theme.edgeMargin : 0
        y: Theme.barHeight + 4
        width: Theme.sidebarWidth
        height: sidebarContent.height + 16
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        onHeightChanged: if (networkWidget.sidebarOpen && networkWidget.popupLayer)
            Qt.callLater(networkWidget.popupLayer.updateInputRegion)

        property real slideOffset: networkWidget.sidebarOpen ? 0 : -12
        transform: Translate { y: sidebar.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Column {
            id: sidebarContent
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 0

            // WiFi section header
            Item {
                width: parent.width
                height: Theme.sectionHeaderHeight

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Text {
                        text: "\uf1eb"
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.iconFontSize
                        color: WiFiService.wifiEnabled ? Theme.dotSelected : Theme.dotEmpty
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        text: "Wi-Fi"
                        color: Theme.textColor
                        font.family: Theme.clockFont
                        font.pixelSize: Theme.textFontSize
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: Theme.wifiTogglePillWidth
                    height: Theme.containerHeight
                    radius: Theme.containerHeight / 2
                    color: WiFiService.wifiEnabled ? Theme.dotSelected : Theme.dotOccupied

                    Text {
                        anchors.centerIn: parent
                        text: WiFiService.wifiEnabled ? "ON" : "OFF"
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize - 2
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: WiFiService.toggleWifi()
                    }
                }
            }

            // Connected network
            Item {
                width: parent.width
                height: WiFiService.connectedSsid ? 28 : 0
                visible: WiFiService.connectedSsid !== ""

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Text {
                        text: "\uf00c"
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.textFontSize
                        color: Theme.dotSelected
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        text: WiFiService.connectedSsid
                        color: Theme.dotSelected
                        font.family: Theme.clockFont
                        font.pixelSize: Theme.textFontSize
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                        elide: Text.ElideRight
                        width: 160
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Repeater {
                        model: 4
                        Rectangle {
                            required property int index
                            width: 4
                            height: 6 + index * 3
                            radius: 2
                            anchors.bottom: parent.bottom
                            color: WiFiService.connectedSignal >= (index + 1) * 25
                                ? Theme.dotSelected : Theme.dotEmpty
                        }
                    }
                }
            }

            // Scanning state
            Text {
                width: parent.width
                visible: WiFiService.wifiEnabled && WiFiService.scanning
                text: "\uf110  Scanning..."
                font.family: Theme.iconFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            Text {
                width: parent.width
                visible: WiFiService.wifiEnabled && !WiFiService.scanning && WiFiService.networks.length === 0
                text: "No networks found"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            // Network list
            Repeater {
                model: WiFiService.wifiEnabled ? Math.min(WiFiService.networks.length, 8) : 0

                delegate: Item {
                    required property int index
                    property var net: WiFiService.networks[index]

                    width: parent.width
                    height: 30

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.containerRadius
                        color: netArea.containsMouse && !net.active ? Theme.menuHover : "transparent"
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Text {
                            text: net.secure ? "\uf023" : "\uf09c"
                            font.family: Theme.iconFont
                            font.pixelSize: Theme.textFontSize
                            color: Theme.dotEmpty
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: net.ssid
                            color: net.active ? Theme.dotSelected : Theme.textColor
                            font.family: Theme.clockFont
                            font.pixelSize: Theme.textFontSize
                            font.bold: net.active
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            width: 180
                        }
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Repeater {
                            model: 4
                            Rectangle {
                                required property int index
                                width: 4
                                height: 6 + index * 3
                                radius: 2
                                anchors.bottom: parent.bottom
                                color: (net.signal ?? 0) >= (index + 1) * 25
                                    ? (net.active ? Theme.dotSelected : Theme.dotOccupied)
                                    : Theme.dotEmpty
                            }
                        }
                    }

                    MouseArea {
                        id: netArea
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !net.active
                        onClicked: WiFiService.connectTo(net.ssid)
                    }
                }
            }
        }
    }
}
