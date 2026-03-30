import QtQuick
import Quickshell
import Quickshell.Bluetooth
import ".."
import "../services"

Rectangle {
    id: networkWidget

    implicitWidth: iconRow.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: barArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool sidebarOpen: false

    // ── Popup layer lookup (same pattern as PowerMenu) ────────────────────
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

    // ── Helper: BT state ─────────────────────────────────────────────────
    readonly property var btAdapter: Bluetooth.defaultAdapter
    readonly property bool btEnabled: btAdapter ? btAdapter.enabled : false
    readonly property bool btConnected: {
        if (!btAdapter) return false;
        for (let i = 0; i < btAdapter.devices.count; i++) {
            if (btAdapter.devices.get(i).modelData.connected) return true;
        }
        return false;
    }

    // ── Bar icons ─────────────────────────────────────────────────────────
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

        Text {
            text: networkWidget.btEnabled ? "\uf294" : "\uf293"
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            anchors.verticalCenter: parent.verticalCenter
            color: {
                if (!networkWidget.btAdapter || !networkWidget.btEnabled) return Theme.dotEmpty;
                return networkWidget.btConnected ? Theme.dotSelected : Theme.textColor;
            }
        }
    }

    MouseArea {
        id: barArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: networkWidget.sidebarOpen = !networkWidget.sidebarOpen
    }

    // ── Sidebar panel ─────────────────────────────────────────────────────
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

            // ── WiFi section header ────────────────────────────────────────
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

                // Toggle pill
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

            // ── Connected network (if any) ─────────────────────────────────
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

                // Signal bars (right side)
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

            // ── Scanning / empty state ─────────────────────────────────────
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

            // ── Network list ───────────────────────────────────────────────
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

                    // Signal bars
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

            // ── Divider ────────────────────────────────────────────────────
            Rectangle {
                width: parent.width
                height: 1
                color: Theme.menuBorder
                visible: networkWidget.btAdapter !== null
            }

            Item { width: parent.width; height: 4 }

            // ── Bluetooth section ──────────────────────────────────────────
            Item {
                width: parent.width
                height: Theme.sectionHeaderHeight
                visible: networkWidget.btAdapter !== null

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Text {
                        text: "\uf294"
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.iconFontSize
                        color: networkWidget.btEnabled ? Theme.dotSelected : Theme.dotEmpty
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        text: "Bluetooth"
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
                    color: networkWidget.btEnabled ? Theme.dotSelected : Theme.dotOccupied

                    Text {
                        anchors.centerIn: parent
                        text: networkWidget.btEnabled ? "ON" : "OFF"
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize - 2
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (networkWidget.btAdapter)
                                networkWidget.btAdapter.enabled = !networkWidget.btAdapter.enabled;
                        }
                    }
                }
            }

            // No BT adapter message
            Text {
                width: parent.width
                visible: networkWidget.btAdapter === null
                text: "No Bluetooth adapter"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            // BT disabled message
            Text {
                width: parent.width
                visible: networkWidget.btAdapter !== null && !networkWidget.btEnabled
                text: "Bluetooth is disabled"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            // ── BT device list ─────────────────────────────────────────────
            Repeater {
                id: btRepeater
                model: (networkWidget.btAdapter && networkWidget.btEnabled)
                    ? networkWidget.btAdapter.devices : null

                delegate: Item {
                    required property var modelData

                    width: parent.width
                    height: 32

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.containerRadius
                        color: btDevArea.containsMouse ? Theme.menuHover : "transparent"
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Text {
                            text: "\uf294"
                            font.family: Theme.iconFont
                            font.pixelSize: Theme.textFontSize
                            color: modelData.connected ? Theme.dotSelected : Theme.dotEmpty
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: modelData.name || modelData.deviceName || modelData.address
                            color: modelData.connected ? Theme.dotSelected : Theme.textColor
                            font.family: Theme.clockFont
                            font.pixelSize: Theme.textFontSize
                            font.bold: modelData.connected
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            width: 160
                        }
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.connected ? "Connected" : (modelData.paired ? "Paired" : "")
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize - 2
                        color: modelData.connected ? Theme.dotSelected : Theme.dotEmpty
                    }

                    MouseArea {
                        id: btDevArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (modelData.connected) modelData.disconnect();
                            else modelData.connect();
                        }
                    }
                }
            }

            // No paired BT devices message
            Text {
                width: parent.width
                visible: networkWidget.btAdapter !== null
                    && networkWidget.btEnabled
                    && btRepeater.count === 0
                text: "No paired devices"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }
        }
    }
}
