import QtQuick
import ".."
import "../services"

Rectangle {
    id: audioWidget

    implicitWidth: pillRow.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: pillArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool popupOpen: false

    readonly property Item popupLayer: {
        let p = parent
        while (p) {
            for (let i = 0; i < p.children.length; i++) {
                if (p.children[i].objectName === "popupLayer") return p.children[i]
            }
            p = p.parent
        }
        return null
    }

    onPopupOpenChanged: if (popupLayer) popupLayer.popupVisible = popupOpen

    Connections {
        target: audioWidget.popupLayer
        function onPopupVisibleChanged() {
            if (audioWidget.popupLayer && !audioWidget.popupLayer.popupVisible)
                audioWidget.popupOpen = false
        }
    }

    // ── Volume icon helper ────────────────────────────────────────────────
    function volumeIcon(vol, muted) {
        if (muted || vol <= 0) return "\uf026"
        if (vol < 0.35)        return "\uf027"
        if (vol < 0.70)        return "\uf028"
        return "\uf028"
    }

    // ── Pill content ──────────────────────────────────────────────────────
    Row {
        id: pillRow
        anchors.centerIn: parent
        spacing: 4

        Text {
            text: audioWidget.volumeIcon(AudioService.masterVolume, AudioService.masterMuted)
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            color: AudioService.masterMuted ? Theme.dotEmpty : Theme.textColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: AudioService.masterMuted ? "muted" : Math.round(AudioService.masterVolume * 100) + "%"
            color: Theme.textColor
            font.family: Theme.monoFont
            font.pixelSize: Theme.textFontSize
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: pillArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: audioWidget.popupOpen = !audioWidget.popupOpen
    }

    // ── Sidebar popup ─────────────────────────────────────────────────────
    Rectangle {
        id: sidebar
        parent: audioWidget.popupLayer
        visible: opacity > 0
        opacity: audioWidget.popupOpen ? 1.0 : 0.0
        x: audioWidget.popupLayer ? audioWidget.popupLayer.width - width - Theme.edgeMargin : 0
        y: Theme.barHeight + 4
        width: Theme.sidebarWidth
        height: Math.min(sidebarScroll.contentHeight + 16, 500)
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        property real slideOffset: audioWidget.popupOpen ? 0 : -12
        transform: Translate { y: sidebar.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Flickable {
            id: sidebarScroll
            anchors.fill: parent
            contentHeight: sidebarContent.implicitHeight + 16
            boundsBehavior: Flickable.StopAtBounds
            clip: true

            Column {
                id: sidebarContent
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 8
                spacing: 0

                // ── Section header helper component ────────────────────────
                component SectionHeader: Item {
                    property string label: ""
                    property string icon:  ""
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
                }

                // ── Volume slider helper ───────────────────────────────────
                component VolumeSlider: Item {
                    id: sliderRoot
                    property real value: 0
                    property bool muted: false
                    property string label: ""
                    property string sublabel: ""
                    property bool isDefault: false
                    signal volumeChanged(real v)
                    signal muteToggled()
                    signal selectClicked()

                    width: parent ? parent.width : 0
                    height: sublabel !== "" ? 64 : 52
                    property bool _dragging: false

                    // Row: bullet/check + label + mute button
                    Row {
                        id: labelRow
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: 6
                        topPadding: 4

                        // Default indicator / select button
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

                        // Mute button
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

                    // Slider track row
                    Item {
                        anchors.top: labelRow.bottom
                        anchors.topMargin: 4
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 22
                        anchors.rightMargin: 4
                        height: 16

                        Rectangle {
                            id: vTrack
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.right: pctTxt.left
                            anchors.rightMargin: 6
                            height: 4
                            radius: 2
                            color: sliderRoot.muted ? Qt.alpha(Theme.mediaProgressTrackBg, 0.5)
                                                    : Theme.mediaProgressTrackBg
                            opacity: sliderRoot.muted ? 0.5 : 1.0

                            Rectangle {
                                width: parent.width * (sliderRoot._dragging ? sliderRoot.value : sliderRoot.value)
                                height: parent.height; radius: 2
                                color: sliderRoot.muted ? Theme.dotOccupied : Theme.mediaProgressColor
                            }
                            Rectangle {
                                width: 12; height: 12; radius: 6
                                color: Theme.buttonBg
                                border.color: Theme.textColor; border.width: 1
                                anchors.verticalCenter: parent.verticalCenter
                                x: Math.max(0, Math.min(vTrack.width - width, sliderRoot.value * vTrack.width - width / 2))
                            }

                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -6
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                function _r(mx) { return Math.max(0, Math.min(1, (mx - 6) / vTrack.width)) }
                                onPressed:  mouse => { sliderRoot._dragging = true;  sliderRoot.volumeChanged(_r(mouse.x)) }
                                onPositionChanged: mouse => { if (pressed) sliderRoot.volumeChanged(_r(mouse.x)) }
                                onReleased: mouse => { sliderRoot._dragging = false; sliderRoot.volumeChanged(_r(mouse.x)) }
                            }
                        }

                        Text {
                            id: pctTxt
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: Math.round(sliderRoot.value * 100) + "%"
                            color: Qt.alpha(Theme.textColor, 0.55)
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize - 2
                            width: 30
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }

                // ══ OUTPUT SECTION ═════════════════════════════════════════
                SectionHeader { label: "Output"; icon: "\uf028" }

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
                        onVolumeChanged: v => AudioService.setSinkVolume(modelData.index, v)
                        onMuteToggled:   AudioService.toggleSinkMute(modelData.index)
                        onSelectClicked: AudioService.setDefaultSink(modelData.name)
                    }
                }

                // Divider
                Rectangle {
                    width: parent.width - 16; height: 1; x: 8
                    color: Qt.alpha(Theme.menuBorder, 0.6)
                    visible: AudioService.sources.length > 0
                }

                // ══ INPUT SECTION ══════════════════════════════════════════
                SectionHeader {
                    label:   "Input"
                    icon:    "\uf130"
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
                        onVolumeChanged: v => AudioService.setSourceVolume(modelData.index, v)
                        onMuteToggled:   AudioService.toggleSourceMute(modelData.index)
                        onSelectClicked: AudioService.setDefaultSource(modelData.name)
                    }
                }

                // Divider
                Rectangle {
                    width: parent.width - 16; height: 1; x: 8
                    color: Qt.alpha(Theme.menuBorder, 0.6)
                    visible: AudioService.sinkInputs.length > 0
                }

                // ══ STREAMS SECTION ════════════════════════════════════════
                SectionHeader {
                    label:   "Streams"
                    icon:    "\uf001"
                    visible: AudioService.sinkInputs.length > 0
                }

                Repeater {
                    model: AudioService.sinkInputs
                    delegate: Item {
                        required property var modelData
                        width:  sidebarContent.width
                        height: streamCol.implicitHeight + 8

                        Column {
                            id: streamCol
                            anchors.fill: parent
                            anchors.topMargin: 4
                            spacing: 4

                            // Stream name + move control row
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
                                    text: modelData.name || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 1
                                    elide: Text.ElideRight
                                    width: parent.width - 80
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                // Mute button
                                Rectangle {
                                    width: 28; height: 22; radius: 5
                                    color: streamMuteBtn.containsMouse ? Theme.menuHover : "transparent"
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.muted ? "\uf6a9" : "\uf028"
                                        font.family: Theme.iconFont
                                        font.pixelSize: 11
                                        color: modelData.muted ? Theme.dotUrgent : Qt.alpha(Theme.textColor, 0.5)
                                    }
                                    MouseArea {
                                        id: streamMuteBtn
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: AudioService.toggleSinkInputMute(modelData.index)
                                    }
                                }
                            }

                            // Volume slider
                            Item {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.leftMargin: 18
                                height: 12

                                Rectangle {
                                    id: stTrack
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.right: stPct.left
                                    anchors.rightMargin: 6
                                    height: 4; radius: 2
                                    color: Theme.mediaProgressTrackBg
                                    opacity: modelData.muted ? 0.4 : 1.0

                                    Rectangle {
                                        width: parent.width * modelData.volume
                                        height: parent.height; radius: 2
                                        color: modelData.muted ? Theme.dotOccupied : Theme.mediaProgressColor
                                    }
                                    Rectangle {
                                        width: 10; height: 10; radius: 5
                                        color: Theme.buttonBg
                                        border.color: Theme.textColor; border.width: 1
                                        anchors.verticalCenter: parent.verticalCenter
                                        x: Math.max(0, Math.min(stTrack.width - width, modelData.volume * stTrack.width - width / 2))
                                    }
                                    MouseArea {
                                        anchors.fill: parent; anchors.margins: -6
                                        hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        function _r(mx) { return Math.max(0, Math.min(1, (mx - 6) / stTrack.width)) }
                                        onPressed: mouse => AudioService.setSinkInputVolume(modelData.index, _r(mouse.x))
                                        onPositionChanged: mouse => { if (pressed) AudioService.setSinkInputVolume(modelData.index, _r(mouse.x)) }
                                        onReleased: mouse => AudioService.setSinkInputVolume(modelData.index, _r(mouse.x))
                                    }
                                }

                                Text {
                                    id: stPct
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Math.round(modelData.volume * 100) + "%"
                                    color: Qt.alpha(Theme.textColor, 0.45)
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 3
                                    width: 30
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            // "Routing: SinkName — move ▾" row
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

                                // Sink selector for this stream
                                Repeater {
                                    model: AudioService.sinks
                                    delegate: Rectangle {
                                        required property var modelData
                                        property var streamData: parent.parent.parent.parent.modelData
                                        height: 20; radius: 4
                                        implicitWidth: sinkLbl.width + 10
                                        color: streamData && modelData.index === streamData.sink_index
                                            ? Theme.dotSelected : moveBtn.containsMouse ? Theme.menuHover : "transparent"

                                        Text {
                                            id: sinkLbl
                                            anchors.centerIn: parent
                                            text: modelData.description.split(" ")[0] || modelData.name
                                            color: parent.streamData && modelData.index === parent.streamData.sink_index
                                                ? "#1a1b26" : Qt.alpha(Theme.textColor, 0.55)
                                            font.family: Theme.monoFont
                                            font.pixelSize: Theme.textFontSize - 3
                                        }
                                        MouseArea {
                                            id: moveBtn
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (parent.streamData)
                                                    AudioService.moveSinkInput(parent.streamData.index, modelData.index)
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
}
