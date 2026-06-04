import QtQuick
import PyShell.Services 1.0
import "../shared"

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
    height: Math.min(settingsScroll.contentHeight + 16,
                     panel.popupLayer ? panel.popupLayer.height - Theme.barHeight - 8 : 680)

    color: Theme.menuBg
    radius: Theme.menuRadius
    border.color: Theme.menuBorder
    border.width: 1
    clip: true

    onHeightChanged: if (panel.panelOpen && panel.popupLayer)
        Qt.callLater(panel.popupLayer.updateInputRegion)
    onVisibleChanged: if (panel.popupLayer)
        Qt.callLater(panel.popupLayer.updateInputRegion)

    property real slideOffset: panel.panelOpen ? 0 : -16
    transform: Translate { y: panel.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    component Divider: Rectangle {
        width: parent ? parent.width - 16 : 0
        x: 8
        height: 1
        color: Qt.alpha(Theme.menuBorder, 0.6)
    }

    component TogglePill: Rectangle {
        id: togglePill
        property bool checked: false
        signal clicked()

        width: Theme.wifiTogglePillWidth
        height: Theme.containerHeight
        radius: Theme.containerHeight / 2
        color: checked ? Theme.dotSelected : Theme.dotOccupied

        Text {
            anchors.centerIn: parent
            text: togglePill.checked ? "ON" : "OFF"
            color: Theme.textColor
            font.family: Theme.monoFont
            font.pixelSize: Theme.textFontSize - 2
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: togglePill.clicked()
        }
    }

    component CollapsibleSection: Column {
        id: section
        property string label: ""
        property string icon: ""
        property bool expanded: true
        property alias rightContent: rightSlot.data
        default property alias sectionContent: body.data

        width: parent ? parent.width : 0
        spacing: 0

        Item {
            width: parent.width
            height: Theme.sectionHeaderHeight

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Text {
                    text: section.expanded ? "\uf078" : "\uf054"
                    font.family: Theme.iconFont
                    font.pixelSize: Theme.textFontSize - 2
                    color: Qt.alpha(Theme.textColor, 0.6)
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: section.icon
                    font.family: Theme.iconFont
                    font.pixelSize: Theme.iconFontSize
                    color: Theme.dotSelected
                    anchors.verticalCenter: parent.verticalCenter
                    visible: section.icon !== ""
                }

                Text {
                    text: section.label
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
                width: childrenRect.width
                height: childrenRect.height
                z: 2
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                z: 1
                onClicked: section.expanded = !section.expanded
            }
        }

        Column {
            id: body
            width: parent.width
            visible: section.expanded
            spacing: 0
        }
    }

    component VolumeSlider: Item {
        id: sliderRoot
        property real value: 0
        property bool muted: false
        property string label: ""
        property string sublabel: ""
        property bool isDefault: false
        signal volumeDragging(real v)
        signal volumeReleased(real v)
        signal muteToggled()
        signal selectClicked()
        readonly property bool dragging: volSlider.isDragging

        width: parent ? parent.width : 0
        height: sublabel !== "" ? 64 : 52

        Row {
            id: labelRow
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6
            topPadding: 4

            Rectangle {
                width: 16; height: 16
                radius: 8
                color: sliderRoot.isDefault ? Theme.dotSelected : "transparent"
                border.color: sliderRoot.isDefault ? Theme.dotSelected : Theme.dotOccupied
                border.width: 1.5
                anchors.verticalCenter: parent.verticalCenter

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: sliderRoot.selectClicked()
                    visible: !sliderRoot.isDefault
                }
            }

            Column {
                width: parent.width - 16 - 28 - 12
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    text: sliderRoot.label
                    color: sliderRoot.isDefault ? Theme.textColor : Qt.alpha(Theme.textColor, 0.7)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 1
                    font.bold: sliderRoot.isDefault
                    elide: Text.ElideRight
                    width: parent.width
                }
                Text {
                    visible: sliderRoot.sublabel !== ""
                    text: sliderRoot.sublabel
                    color: Qt.alpha(Theme.textColor, 0.45)
                    font.family: Theme.clockFont
                    font.pixelSize: Theme.textFontSize - 2
                    elide: Text.ElideRight
                    width: parent.width
                }
            }

            Rectangle {
                width: 28; height: 24; radius: 6
                color: muteBtn.containsMouse ? Theme.menuHover : "transparent"
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    anchors.centerIn: parent
                    text: sliderRoot.muted ? "\uf6a9" : "\uf028"
                    font.family: Theme.iconFont
                    font.pixelSize: 12
                    color: sliderRoot.muted ? Theme.dotUrgent : Qt.alpha(Theme.textColor, 0.55)
                }
                MouseArea {
                    id: muteBtn
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: sliderRoot.muteToggled()
                }
            }
        }

        Item {
            anchors.top: labelRow.bottom
            anchors.topMargin: 4
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 22
            anchors.rightMargin: 4
            height: 16

            SmoothSlider {
                id: volSlider
                anchors.left: parent.left
                anchors.right: pctTxt.left
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                value: sliderRoot.value
                opacity: sliderRoot.muted ? 0.5 : 1.0
                fillColor: sliderRoot.muted ? Theme.dotOccupied : Theme.mediaProgressColor
                onDragging: v => sliderRoot.volumeDragging(v)
                onReleased: v => sliderRoot.volumeReleased(v)
            }

            Text {
                id: pctTxt
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: Math.round(volSlider.displayValue * 100) + "%"
                color: Qt.alpha(Theme.textColor, 0.55)
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize - 2
                width: 30
                horizontalAlignment: Text.AlignRight
            }
        }
    }

    Flickable {
        id: settingsScroll
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

            CollapsibleSection {
                label: "Wi-Fi"
                icon: "\uf1eb"

                rightContent: [
                    TogglePill {
                        checked: WiFiService.wifiEnabled
                        onClicked: WiFiService.toggleWifi()
                    }
                ]

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
                            width: 200
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
                                width: 210
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
                            cursorShape: Qt.PointingHandCursor
                            onClicked: WiFiService.connectTo(net.ssid)
                        }
                    }
                }
            }

            Divider {}

            CollapsibleSection {
                label: "Bluetooth"
                icon: "\uf294"

                rightContent: [
                    Row {
                        spacing: 6

                        Rectangle {
                            visible: BluetoothService.enabled
                            width: Theme.wifiTogglePillWidth
                            height: Theme.containerHeight
                            radius: Theme.containerHeight / 2
                            color: btScanArea.containsMouse ? Theme.menuHover : Theme.containerBg

                            Text {
                                anchors.centerIn: parent
                                text: BluetoothService.scanning ? "\uf110" : "\uf021"
                                font.family: Theme.iconFont
                                font.pixelSize: Theme.textFontSize
                                color: Theme.textColor
                            }

                            MouseArea {
                                id: btScanArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: BluetoothService.startScan()
                            }
                        }

                        TogglePill {
                            checked: BluetoothService.enabled
                            onClicked: BluetoothService.toggleBluetooth()
                        }
                    }
                ]

                Item {
                    width: parent.width
                    height: BluetoothService.connectedDevice !== "" ? 28 : 0
                    visible: BluetoothService.connectedDevice !== ""

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Text {
                            text: "\uf025"
                            font.family: Theme.iconFont
                            font.pixelSize: Theme.textFontSize
                            color: Theme.dotSelected
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: BluetoothService.connectedDevice
                            color: Theme.dotSelected
                            font.family: Theme.clockFont
                            font.pixelSize: Theme.textFontSize
                            font.bold: true
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            width: 240
                        }
                    }
                }

                Repeater {
                    model: BluetoothService.enabled ? BluetoothService.devices : []

                    delegate: Item {
                        required property int index
                        property var dev: BluetoothService.devices[index]

                        width: parent.width
                        height: 30

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
                                text: {
                                    var ic = dev ? (dev.icon || "") : ""
                                    if (ic.indexOf("audio") >= 0) return "\uf025"
                                    if (ic.indexOf("input-keyboard") >= 0) return "\uf11c"
                                    if (ic.indexOf("input-mouse") >= 0) return "\uf245"
                                    if (ic.indexOf("phone") >= 0) return "\uf10b"
                                    return "\uf294"
                                }
                                font.family: Theme.iconFont
                                font.pixelSize: Theme.textFontSize
                                color: (dev && dev.connected) ? Theme.dotSelected : Theme.dotEmpty
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: dev ? (dev.name || dev.address || "") : ""
                                color: (dev && dev.connected) ? Theme.dotSelected : Theme.textColor
                                font.family: Theme.clockFont
                                font.pixelSize: Theme.textFontSize
                                font.bold: dev ? dev.connected : false
                                anchors.verticalCenter: parent.verticalCenter
                                elide: Text.ElideRight
                                width: 220
                            }
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: (dev && dev.connected) ? "\uf127" : "\uf293"
                            font.family: Theme.iconFont
                            font.pixelSize: Theme.textFontSize - 2
                            color: Qt.alpha(Theme.textColor, 0.5)
                        }

                        MouseArea {
                            id: btDevArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (dev && dev.connected)
                                    BluetoothService.disconnectDevice(dev.address)
                                else if (dev)
                                    BluetoothService.connectDevice(dev.address)
                            }
                        }
                    }
                }
            }

            Divider {}

            CollapsibleSection {
                label: "Audio"
                icon: "\uf028"

                Text {
                    width: parent.width
                    visible: AudioService.sinks.length === 0
                    text: "No output devices"
                    font.family: Theme.clockFont
                    font.pixelSize: Theme.textFontSize
                    color: Theme.dotEmpty
                    bottomPadding: 6
                }

                Text {
                    width: parent.width
                    text: "Output"
                    color: Qt.alpha(Theme.textColor, 0.55)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 2
                    topPadding: 2
                    bottomPadding: 2
                    visible: AudioService.sinks.length > 0
                }

                Repeater {
                    model: AudioService.sinks
                    delegate: VolumeSlider {
                        required property var modelData
                        label: modelData.description || modelData.name
                        value: modelData.volume
                        muted: modelData.muted
                        isDefault: modelData.name === AudioService.defaultSink
                        onDraggingChanged: dragging ? AudioService.beginDrag() : AudioService.endDrag()
                        onVolumeDragging: v => AudioService.applySinkVolume(modelData.index, v)
                        onVolumeReleased: v => AudioService.setSinkVolume(modelData.index, v)
                        onMuteToggled: AudioService.toggleSinkMute(modelData.index)
                        onSelectClicked: AudioService.setDefaultSink(modelData.name)
                    }
                }

                Divider { visible: AudioService.sources.length > 0 }

                Text {
                    width: parent.width
                    text: "Input"
                    color: Qt.alpha(Theme.textColor, 0.55)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 2
                    topPadding: 6
                    bottomPadding: 2
                    visible: AudioService.sources.length > 0
                }

                Repeater {
                    model: AudioService.sources
                    delegate: VolumeSlider {
                        required property var modelData
                        label: modelData.description || modelData.name
                        value: modelData.volume
                        muted: modelData.muted
                        isDefault: modelData.name === AudioService.defaultSource
                        onDraggingChanged: dragging ? AudioService.beginDrag() : AudioService.endDrag()
                        onVolumeDragging: v => AudioService.applySourceVolume(modelData.index, v)
                        onVolumeReleased: v => AudioService.setSourceVolume(modelData.index, v)
                        onMuteToggled: AudioService.toggleSourceMute(modelData.index)
                        onSelectClicked: AudioService.setDefaultSource(modelData.name)
                    }
                }

                Divider { visible: AudioService.sinkInputs.length > 0 }

                Text {
                    width: parent.width
                    text: "Streams"
                    color: Qt.alpha(Theme.textColor, 0.55)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 2
                    topPadding: 6
                    bottomPadding: 2
                    visible: AudioService.sinkInputs.length > 0
                }

                Repeater {
                    model: AudioService.sinkInputs
                    delegate: Item {
                        id: streamDelegate
                        required property var modelData
                        width: parent.width
                        height: streamCol.implicitHeight + 8

                        Column {
                            id: streamCol
                            anchors.fill: parent
                            anchors.topMargin: 4
                            spacing: 4

                            Row {
                                width: parent.width
                                spacing: 6

                                Text {
                                    text: "\uf001"
                                    font.family: Theme.iconFont
                                    font.pixelSize: 11
                                    color: Qt.alpha(Theme.textColor, 0.4)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    text: streamDelegate.modelData.name || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 1
                                    elide: Text.ElideRight
                                    width: parent.width - 80
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Rectangle {
                                    width: 28; height: 22; radius: 5
                                    color: streamMuteBtn.containsMouse ? Theme.menuHover : "transparent"
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        anchors.centerIn: parent
                                        text: streamDelegate.modelData.muted ? "\uf6a9" : "\uf028"
                                        font.family: Theme.iconFont
                                        font.pixelSize: 11
                                        color: streamDelegate.modelData.muted ? Theme.dotUrgent : Qt.alpha(Theme.textColor, 0.5)
                                    }
                                    MouseArea {
                                        id: streamMuteBtn
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: AudioService.toggleSinkInputMute(streamDelegate.modelData.index)
                                    }
                                }
                            }

                            Item {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.leftMargin: 18
                                height: 12

                                SmoothSlider {
                                    id: streamSlider
                                    anchors.left: parent.left
                                    anchors.right: stPct.left
                                    anchors.rightMargin: 6
                                    anchors.verticalCenter: parent.verticalCenter
                                    thumbSize: 10
                                    value: streamDelegate.modelData.volume
                                    opacity: streamDelegate.modelData.muted ? 0.4 : 1.0
                                    fillColor: streamDelegate.modelData.muted ? Theme.dotOccupied : Theme.mediaProgressColor
                                    onIsDraggingChanged: isDragging ? AudioService.beginDrag() : AudioService.endDrag()
                                    onDragging: v => AudioService.applySinkInputVolume(streamDelegate.modelData.index, v)
                                    onReleased: v => AudioService.setSinkInputVolume(streamDelegate.modelData.index, v)
                                }

                                Text {
                                    id: stPct
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Math.round(streamSlider.displayValue * 100) + "%"
                                    color: Qt.alpha(Theme.textColor, 0.45)
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 3
                                    width: 30
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            Row {
                                anchors.left: parent.left
                                anchors.leftMargin: 18
                                spacing: 4
                                visible: AudioService.sinks.length > 1

                                Text {
                                    text: "\uf144"
                                    font.family: Theme.iconFont
                                    font.pixelSize: 10
                                    color: Qt.alpha(Theme.textColor, 0.35)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Repeater {
                                    model: AudioService.sinks
                                    delegate: Rectangle {
                                        required property var modelData
                                        height: 20; radius: 4
                                        implicitWidth: sinkLbl.width + 10
                                        color: modelData.index === streamDelegate.modelData.sink_index
                                            ? Theme.dotSelected : moveBtn.containsMouse ? Theme.menuHover : "transparent"

                                        Text {
                                            id: sinkLbl
                                            anchors.centerIn: parent
                                            text: modelData.description.split(" ")[0] || modelData.name
                                            color: modelData.index === streamDelegate.modelData.sink_index
                                                ? "#1a1b26" : Qt.alpha(Theme.textColor, 0.55)
                                            font.family: Theme.monoFont
                                            font.pixelSize: Theme.textFontSize - 3
                                        }
                                        MouseArea {
                                            id: moveBtn
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: AudioService.moveSinkInput(streamDelegate.modelData.index, modelData.index)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Divider {}

            CollapsibleSection {
                label: "Brightness"
                icon: "\uf185"

                Text {
                    width: parent.width
                    visible: BrightnessService.displays.length === 0
                    text: "No displays detected"
                    font.family: Theme.clockFont
                    font.pixelSize: Theme.textFontSize
                    color: Theme.dotEmpty
                    topPadding: 4
                    bottomPadding: 8
                }

                Repeater {
                    model: BrightnessService.displays

                    Item {
                        required property var modelData
                        width: parent.width
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
                                    width: parent.width - pctLabel.width - 6
                                }

                                Text {
                                    id: pctLabel
                                    text: Math.round(brightnessSlider.displayValue * 100) + "%"
                                    color: Theme.dotSelected
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 1
                                    font.bold: true
                                }
                            }

                            SmoothSlider {
                                id: brightnessSlider
                                width: parent.width
                                value: modelData.brightness
                                min: 0.05
                                onDragging: v => BrightnessService.applyBrightness(modelData.name, v)
                                onReleased: v => BrightnessService.setDisplay(modelData.name, v)
                            }
                        }
                    }
                }
            }

            Divider {}

            CollapsibleSection {
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
                            cursorShape: Qt.PointingHandCursor
                            onClicked: NotificationService.dismissAll()
                        }
                    }
                ]

                Rectangle {
                    width: parent.width
                    height: 220
                    radius: Theme.containerRadius
                    color: Qt.alpha(Theme.containerBg, 0.35)
                    clip: true

                    Flickable {
                        id: notificationScroll
                        anchors.fill: parent
                        anchors.margins: 4
                        contentHeight: notificationContent.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true

                        Column {
                            id: notificationContent
                            width: notificationScroll.width
                            spacing: 0

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

                                    width: notificationContent.width
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
                                                        cursorShape: Qt.PointingHandCursor
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
                        }
                    }
                }
            }

            Item { width: parent.width; height: 8 }
        }
    }
}
