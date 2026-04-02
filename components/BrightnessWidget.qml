import QtQuick
import ".."
import "../services"

Rectangle {
    id: brightnessWidget

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
        target: brightnessWidget.popupLayer
        function onPopupVisibleChanged() {
            if (brightnessWidget.popupLayer && !brightnessWidget.popupLayer.popupVisible)
                brightnessWidget.popupOpen = false
        }
    }

    // ── Pill content ──────────────────────────────────────────────────────
    Row {
        id: pillRow
        anchors.centerIn: parent
        spacing: 4

        Text {
            text: "\uf185"
            font.family: Theme.iconFont
            font.pixelSize: Theme.iconFontSize
            color: Theme.textColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: {
                if (BrightnessService.displays.length === 0) return "–"
                const avg = BrightnessService.displays.reduce((s, d) => s + d.brightness, 0)
                    / BrightnessService.displays.length
                return Math.round(avg * 100) + "%"
            }
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
        onClicked: brightnessWidget.popupOpen = !brightnessWidget.popupOpen
    }

    // ── Popup panel ───────────────────────────────────────────────────────
    Rectangle {
        id: popup
        parent: brightnessWidget.popupLayer
        visible: opacity > 0
        opacity: brightnessWidget.popupOpen ? 1.0 : 0.0
        x: brightnessWidget.popupLayer ? brightnessWidget.popupLayer.width - width - Theme.edgeMargin : 0
        y: Theme.barHeight + 4
        width: 280
        height: popupContent.implicitHeight + 16
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        property real slideOffset: brightnessWidget.popupOpen ? 0 : -12
        transform: Translate { y: popup.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Column {
            id: popupContent
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 0

            // Header
            Item {
                width: parent.width
                height: Theme.sectionHeaderHeight

                Text {
                    text: "\uf185  Brightness"
                    font.family: Theme.iconFont
                    font.pixelSize: Theme.textFontSize
                    font.bold: true
                    color: Theme.textColor
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            // Empty state
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

            // Per-display slider rows
            Repeater {
                model: BrightnessService.displays

                Item {
                    id: displayItem
                    required property var modelData
                    required property int index

                    property real dragValue: modelData.brightness
                    property bool isDragging: false
                    readonly property real displayBrightness: isDragging ? dragValue : modelData.brightness

                    // Keep dragValue in sync when not dragging (external brightness changes)
                    onModelDataChanged: if (!isDragging) dragValue = modelData.brightness

                    width: popupContent.width
                    height: 52

                    // Fires every 16ms while isDragging — calls applyBrightness (no array churn)
                    // repeat:true/running binding means it self-manages: no restart() needed
                    Timer {
                        id: applyTimer
                        interval: 16
                        repeat: true
                        running: displayItem.isDragging
                        onTriggered: BrightnessService.applyBrightness(
                            displayItem.modelData.name, displayItem.dragValue)
                    }

                    Column {
                        id: displayColumn
                        anchors.fill: parent
                        anchors.leftMargin: 4
                        anchors.rightMargin: 4
                        spacing: 6

                        // Display name + percentage
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
                                text: Math.round(displayItem.displayBrightness * 100) + "%"
                                color: Theme.dotSelected
                                font.family: Theme.monoFont
                                font.pixelSize: Theme.textFontSize - 1
                                font.bold: true
                            }
                        }

                        // Slider track (visual only — interaction handled by fullAreaMouse below)
                        Rectangle {
                            id: track
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Theme.mediaProgressTrackBg

                            Rectangle {
                                width: parent.width * displayItem.displayBrightness
                                height: parent.height
                                radius: 2
                                color: Theme.mediaProgressColor
                            }

                            Rectangle {
                                id: thumb
                                width: 12; height: 12; radius: 6
                                color: Theme.buttonBg
                                border.color: Theme.textColor
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter
                                x: Math.max(0, Math.min(track.width - width,
                                    displayItem.displayBrightness * track.width - width / 2))
                            }
                        }
                    }

                    // Full-height MouseArea so vertical drift never breaks the grab.
                    // QML maintains the mouse grab outside bounds once pressed, so
                    // the user can drag anywhere in the popup and keep control.
                    MouseArea {
                        id: fullAreaMouse
                        anchors.fill: parent
                        preventStealing: true
                        cursorShape: Qt.PointingHandCursor

                        // mouse.x is in displayItem coords; track starts at column leftMargin (4px)
                        function _ratio(mx) {
                            return Math.max(0.05, Math.min(1.0, (mx - 4) / track.width))
                        }

                        onPressed: mouse => {
                            displayItem.dragValue = _ratio(mouse.x)
                            displayItem.isDragging = true
                        }
                        onPositionChanged: mouse => {
                            if (pressed) displayItem.dragValue = _ratio(mouse.x)
                        }
                        onReleased: mouse => {
                            displayItem.isDragging = false
                            BrightnessService.setDisplay(displayItem.modelData.name, displayItem.dragValue)
                        }
                    }
                }
            }

            // Bottom padding
            Item { width: parent.width; height: 4 }
        }
    }
}
