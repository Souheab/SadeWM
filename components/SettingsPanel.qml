import QtQuick
import Quickshell
import Quickshell.Bluetooth
import ".."
import "../services"

// Full-height settings panel anchored to the right side of the screen.
// Contains: Notifications, Volume, Brightness, Wi-Fi, Bluetooth.
Rectangle {
    id: panel

    property Item popupLayer: null
    property bool panelOpen: false

    signal closeRequested()

    parent: panel.popupLayer
    visible: opacity > 0
    opacity: panel.panelOpen ? 1.0 : 0.0

    x: panel.popupLayer ? panel.popupLayer.width - width - Theme.edgeMargin : 0
    y: Theme.barHeight + 4
    width: Theme.settingsPanelWidth
    height: panel.popupLayer ? panel.popupLayer.height - Theme.barHeight - 8 : 0

    color: Theme.menuBg
    radius: Theme.menuRadius
    border.color: Theme.menuBorder
    border.width: 1
    clip: true

    property real slideOffset: panel.panelOpen ? 0 : -16
    transform: Translate { y: panel.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    // ── BT state helpers ────────────────────────────────────────────────────
    readonly property var btAdapter: Bluetooth.defaultAdapter
    readonly property bool btEnabled: btAdapter ? btAdapter.enabled : false

    // ── Shared section header component ─────────────────────────────────────
    component SectionHeader: Item {
        property string label: ""
        property string icon: ""
        property alias rightContent: rightSlot.data

        width: parent ? parent.width : 0
        height: Theme.sectionHeaderHeight

        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text {
                text: icon
                font.family: Theme.iconFont
                font.pixelSize: Theme.iconFontSize
                color: Theme.dotSelected
                anchors.verticalCenter: parent.verticalCenter
                visible: icon !== ""
            }
            Text {
                text: label
                color: Theme.textColor
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Item {
            id: rightSlot
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    // ── Toggle pill ──────────────────────────────────────────────────────────
    component TogglePill: Rectangle {
        property bool checked: false
        signal toggled()

        width: Theme.wifiTogglePillWidth
        height: Theme.containerHeight
        radius: Theme.containerHeight / 2
        color: checked ? Theme.dotSelected : Theme.dotOccupied

        Text {
            anchors.centerIn: parent
            text: parent.checked ? "ON" : "OFF"
            color: Theme.textColor
            font.family: Theme.monoFont
            font.pixelSize: Theme.textFontSize - 2
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
            onClicked: parent.toggled()
        }
    }

    // ── Divider ──────────────────────────────────────────────────────────────
    component Divider: Rectangle {
        width: parent ? parent.width - 16 : 0
        x: 8
        height: 1
        color: Qt.alpha(Theme.menuBorder, 0.6)
    }

    // ── Volume slider (reused from AudioWidget) ──────────────────────────────
    component VolumeSlider: Item {
        id: vsRoot
        property real value: 0
        property bool muted: false
        property string label: ""
        property string sublabel: ""
        property bool isDefault: false
        signal volumeDragging(real v)
        signal volumeReleased(real v)
        signal muteToggled()
        signal selectClicked()
        readonly property bool dragging: vsSlider.isDragging

        width: parent ? parent.width : 0
        height: sublabel !== "" ? 64 : 52

        Row {
            id: vsLabelRow
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6
            topPadding: 4

            Rectangle {
                width: 16; height: 16
                radius: 8
                color: vsRoot.isDefault ? Theme.dotSelected : "transparent"
                border.color: vsRoot.isDefault ? Theme.dotSelected : Theme.dotOccupied
                border.width: 1.5
                anchors.verticalCenter: parent.verticalCenter

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: vsRoot.selectClicked()
                    visible: !vsRoot.isDefault
                }
            }

            Column {
                width: parent.width - 16 - 28 - 12
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    text: vsRoot.label
                    color: vsRoot.isDefault ? Theme.textColor : Qt.alpha(Theme.textColor, 0.7)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 1
                    font.bold: vsRoot.isDefault
                    elide: Text.ElideRight
                    width: parent.width
                }
                Text {
                    visible: vsRoot.sublabel !== ""
                    text: vsRoot.sublabel
                    color: Qt.alpha(Theme.textColor, 0.45)
                    font.family: Theme.clockFont
                    font.pixelSize: Theme.textFontSize - 2
                    elide: Text.ElideRight
                    width: parent.width
                }
            }

            Rectangle {
                width: 28; height: 24; radius: 6
                color: vsMuteBtn.containsMouse ? Theme.menuHover : "transparent"
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    anchors.centerIn: parent
                    text: vsRoot.muted ? "\uf6a9" : "\uf028"
                    font.family: Theme.iconFont
                    font.pixelSize: 12
                    color: vsRoot.muted ? Theme.dotUrgent : Qt.alpha(Theme.textColor, 0.55)
                }
                MouseArea {
                    id: vsMuteBtn
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: vsRoot.muteToggled()
                }
            }
        }

        Item {
            anchors.top: vsLabelRow.bottom
            anchors.topMargin: 4
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 22
            anchors.rightMargin: 4
            height: 16

            SmoothSlider {
                id: vsSlider
                anchors.left: parent.left
                anchors.right: vsPctTxt.left
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                value: vsRoot.value
                opacity: vsRoot.muted ? 0.5 : 1.0
                fillColor: vsRoot.muted ? Theme.dotOccupied : Theme.mediaProgressColor
                onDragging: v => vsRoot.volumeDragging(v)
                onReleased: v => vsRoot.volumeReleased(v)
            }

            Text {
                id: vsPctTxt
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: Math.round(vsSlider.displayValue * 100) + "%"
                color: Qt.alpha(Theme.textColor, 0.55)
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize - 2
                width: 30
                horizontalAlignment: Text.AlignRight
            }
        }
    }

    // ── Main scrollable content ──────────────────────────────────────────────
    Flickable {
        id: scroll
        anchors.fill: parent
        contentHeight: content.implicitHeight + 16
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Column {
            id: content
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 0

            // ══ NOTIFICATIONS ═══════════════════════════════════════════════
            SectionHeader {
                label: "Notifications"
                icon: "\uf0f3"

                rightContent: [
                    Rectangle {
                        width: 60
                        height: 22
                        radius: 6
                        color: clearHover.containsMouse ? Theme.menuHover : "transparent"
                        border.color: Qt.alpha(Theme.menuBorder, 0.6)
                        border.width: 1
                        visible: NotificationService.notifications.length > 0
                        anchors.verticalCenter: parent.verticalCenter

                        Text {
                            anchors.centerIn: parent
                            text: "Clear all"
                            color: Qt.alpha(Theme.textColor, 0.65)
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize - 3
                        }

                        MouseArea {
                            id: clearHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: NotificationService.dismissAll()
                        }
                    }
                ]
            }

            // Empty state
            Item {
                width: parent.width
                height: 44
                visible: NotificationService.notifications.length === 0

                Text {
                    anchors.centerIn: parent
                    text: "No notifications"
                    color: Qt.alpha(Theme.textColor, 0.35)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 1
                }
            }

            Repeater {
                model: NotificationService.notifications.length
                delegate: Item {
                    id: notifItem
                    required property int index
                    property var notif: NotificationService.notifications[index]

                    width: content.width
                    height: notifCard.height + 4

                    Rectangle {
                        id: notifCard
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 2
                        height: notifCardContent.implicitHeight + 12
                        radius: Theme.containerRadius
                        color: notifArea.containsMouse ? Theme.menuHover : Qt.alpha(Theme.containerBg, 0.7)

                        Column {
                            id: notifCardContent
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 8
                            anchors.topMargin: 8
                            spacing: 3

                            Row {
                                width: parent.width
                                spacing: 6

                                Text {
                                    text: notifItem.notif ? (notifItem.notif.appName || "App") : "App"
                                    color: Qt.alpha(Theme.textColor, 0.5)
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 3
                                    anchors.verticalCenter: parent.verticalCenter
                                    elide: Text.ElideRight
                                    width: parent.width - dismissBtn.width - 6
                                }

                                Rectangle {
                                    id: dismissBtn
                                    width: 16; height: 16; radius: 8
                                    color: dismissArea.containsMouse ? Qt.alpha(Theme.dotUrgent, 0.2) : "transparent"
                                    anchors.verticalCenter: parent.verticalCenter

                                    Text {
                                        anchors.centerIn: parent
                                        text: "\uf00d"
                                        font.family: Theme.iconFont
                                        font.pixelSize: 9
                                        color: Qt.alpha(Theme.textColor, 0.4)
                                    }

                                    MouseArea {
                                        id: dismissArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        onClicked: NotificationService.dismiss(notifItem.index)
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                text: notifItem.notif ? (notifItem.notif.summary || "") : ""
                                color: Theme.textColor
                                font.family: Theme.clockFont
                                font.pixelSize: Theme.textFontSize
                                font.bold: true
                                wrapMode: Text.WordWrap
                                visible: text !== ""
                            }

                            Text {
                                width: parent.width
                                text: notifItem.notif ? (notifItem.notif.body || "") : ""
                                color: Qt.alpha(Theme.textColor, 0.72)
                                font.family: Theme.monoFont
                                font.pixelSize: Theme.textFontSize - 1
                                wrapMode: Text.WordWrap
                                maximumLineCount: 4
                                elide: Text.ElideRight
                                visible: text !== ""
                            }
                        }

                        MouseArea {
                            id: notifArea
                            anchors.fill: parent
                            hoverEnabled: true
                            z: -1
                        }
                    }
                }
            }

            Divider { visible: true }

            // ══ VOLUME ══════════════════════════════════════════════════════
            SectionHeader { label: "Volume"; icon: "\uf028" }

            Text {
                width: parent.width
                visible: AudioService.sinks.length === 0
                text: "No output devices"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                bottomPadding: 6
            }

            Repeater {
                model: AudioService.sinks
                delegate: VolumeSlider {
                    required property var modelData
                    label:     modelData.description || modelData.name
                    value:     modelData.volume
                    muted:     modelData.muted
                    isDefault: modelData.name === AudioService.defaultSink
                    onDraggingChanged: dragging ? AudioService.beginDrag() : AudioService.endDrag()
                    onVolumeDragging: v => AudioService.applySinkVolume(modelData.index, v)
                    onVolumeReleased: v => AudioService.setSinkVolume(modelData.index, v)
                    onMuteToggled:   AudioService.toggleSinkMute(modelData.index)
                    onSelectClicked: AudioService.setDefaultSink(modelData.name)
                }
            }

            Rectangle {
                width: parent.width - 16; height: 1; x: 8
                color: Qt.alpha(Theme.menuBorder, 0.6)
                visible: AudioService.sources.length > 0
            }

            SectionHeader {
                label: "Input"
                icon: "\uf130"
                visible: AudioService.sources.length > 0
            }

            Repeater {
                model: AudioService.sources
                delegate: VolumeSlider {
                    required property var modelData
                    label:     modelData.description || modelData.name
                    value:     modelData.volume
                    muted:     modelData.muted
                    isDefault: modelData.name === AudioService.defaultSource
                    onDraggingChanged: dragging ? AudioService.beginDrag() : AudioService.endDrag()
                    onVolumeDragging: v => AudioService.applySourceVolume(modelData.index, v)
                    onVolumeReleased: v => AudioService.setSourceVolume(modelData.index, v)
                    onMuteToggled:   AudioService.toggleSourceMute(modelData.index)
                    onSelectClicked: AudioService.setDefaultSource(modelData.name)
                }
            }

            Divider {}

            // ══ BRIGHTNESS ══════════════════════════════════════════════════
            SectionHeader { label: "Brightness"; icon: "\uf185" }

            Text {
                width: parent.width
                visible: BrightnessService.displays.length === 0
                text: "No displays detected"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                bottomPadding: 6
            }

            Repeater {
                model: BrightnessService.displays
                delegate: Item {
                    required property var modelData
                    required property int index

                    width: content.width
                    height: 52

                    Column {
                        anchors.fill: parent
                        anchors.leftMargin: 4
                        anchors.rightMargin: 4
                        spacing: 6

                        Row {
                            width: parent.width
                            spacing: 6

                            Text {
                                text: modelData.name
                                color: Theme.textColor
                                font.family: Theme.monoFont
                                font.pixelSize: Theme.textFontSize - 1
                                elide: Text.ElideRight
                                width: parent.width - bPctLbl.width - 6
                            }

                            Text {
                                id: bPctLbl
                                text: Math.round(bSlider.displayValue * 100) + "%"
                                color: Theme.dotSelected
                                font.family: Theme.monoFont
                                font.pixelSize: Theme.textFontSize - 1
                                font.bold: true
                            }
                        }

                        SmoothSlider {
                            id: bSlider
                            width: parent.width
                            value: modelData.brightness
                            min: 0.05
                            onDragging: v => BrightnessService.applyBrightness(modelData.name, v)
                            onReleased: v => BrightnessService.setDisplay(modelData.name, v)
                        }
                    }
                }
            }

            Divider {}

            // ══ WI-FI ═══════════════════════════════════════════════════════
            SectionHeader {
                label: "Wi-Fi"
                icon: "\uf1eb"

                rightContent: [
                    TogglePill {
                        checked: WiFiService.wifiEnabled
                        onToggled: WiFiService.toggleWifi()
                        anchors.verticalCenter: parent.verticalCenter
                    }
                ]
            }

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

            Repeater {
                model: WiFiService.wifiEnabled ? Math.min(WiFiService.networks.length, 8) : 0

                delegate: Item {
                    required property int index
                    property var net: WiFiService.networks[index]

                    width: content.width
                    height: 30

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.containerRadius
                        color: wNetArea.containsMouse && !net.active ? Theme.menuHover : "transparent"
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
                            width: 170
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
                        id: wNetArea
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !net.active
                        onClicked: WiFiService.connectTo(net.ssid)
                    }
                }
            }

            Divider {}

            // ══ BLUETOOTH ═══════════════════════════════════════════════════
            SectionHeader {
                label: "Bluetooth"
                icon: "\uf294"
                visible: panel.btAdapter !== null

                rightContent: [
                    TogglePill {
                        checked: panel.btEnabled
                        onToggled: {
                            if (panel.btAdapter)
                                panel.btAdapter.enabled = !panel.btAdapter.enabled
                        }
                        anchors.verticalCenter: parent.verticalCenter
                        visible: panel.btAdapter !== null
                    }
                ]
            }

            Text {
                width: parent.width
                visible: panel.btAdapter === null
                text: "No Bluetooth adapter"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            Text {
                width: parent.width
                visible: panel.btAdapter !== null && !panel.btEnabled
                text: "Bluetooth is disabled"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            Repeater {
                id: btDevRepeater
                model: (panel.btAdapter && panel.btEnabled) ? panel.btAdapter.devices : null

                delegate: Item {
                    required property var modelData

                    width: content.width
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
                            text: modelData.name || modelData.address || "Unknown"
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
                            if (modelData.connected) modelData.disconnect()
                            else modelData.connect()
                        }
                    }
                }
            }

            Text {
                width: parent.width
                visible: panel.btAdapter !== null && panel.btEnabled && btDevRepeater.count === 0
                text: "No paired devices"
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                color: Theme.dotEmpty
                topPadding: 4
                bottomPadding: 4
            }

            Item { width: parent.width; height: 8 }
        }
    }
}
