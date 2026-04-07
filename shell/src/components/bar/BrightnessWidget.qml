import QtQuick
import PyShell.Services 1.0
import "../shared"

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
        cursorShape: Qt.PointingHandCursor
        onClicked: brightnessWidget.popupOpen = !brightnessWidget.popupOpen
    }

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

        onHeightChanged: if (brightnessWidget.popupOpen && brightnessWidget.popupLayer)
            Qt.callLater(brightnessWidget.popupLayer.updateInputRegion)
        onVisibleChanged: if (brightnessWidget.popupLayer)
            Qt.callLater(brightnessWidget.popupLayer.updateInputRegion)

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

            Item {
                width: parent.width
                height: Theme.sectionHeaderHeight

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Text {
                        text: "\uf185"
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.iconFontSize
                        color: Theme.dotSelected
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        text: "Brightness"
                        color: Theme.textColor
                        font.family: Theme.clockFont
                        font.pixelSize: Theme.textFontSize
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

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
                    required property int index

                    width: popupContent.width
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
                            min:   0.05
                            onDragging: v => BrightnessService.applyBrightness(modelData.name, v)
                            onReleased: v => BrightnessService.setDisplay(modelData.name, v)
                        }
                    }
                }
            }

            Item { width: parent.width; height: 4 }
        }
    }
}
