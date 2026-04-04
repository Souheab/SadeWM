import QtQuick
import PyShell.Services 1.0

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
    height: Math.min(content.implicitHeight + 16, panel.popupLayer ? panel.popupLayer.height - Theme.barHeight - 8 : 600)

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
            width: childrenRect.width
        }
    }

    component Divider: Rectangle {
        width: parent ? parent.width - 16 : 0
        x: 8
        height: 1
        color: Qt.alpha(Theme.menuBorder, 0.6)
    }

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

            Item { width: parent.width; height: 8 }
        }
    }
}
