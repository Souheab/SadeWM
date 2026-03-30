import QtQuick
import Quickshell
import Quickshell.Widgets
import ".."
import "../services"

// Launcher dropdown — reparented to the popup layer.
// Instantiate inside WorkspaceDots and pass popupLayer + open state.
Rectangle {
    id: launcher

    // Set by parent (WorkspaceDots)
    property Item popupLayer: null
    property bool launcherOpen: false
    property real anchorX: 0
    property real anchorY: 0

    parent: launcher.popupLayer
    visible: opacity > 0
    opacity: launcher.launcherOpen ? 1.0 : 0.0
    x: launcher.anchorX
    y: launcher.anchorY

    width: Theme.launcherWidth
    height: Math.min(contentCol.implicitHeight, Theme.launcherMaxHeight)

    color: Theme.menuBg
    radius: Theme.menuRadius
    border.color: Theme.menuBorder
    border.width: 1
    clip: true

    property real slideOffset: launcher.launcherOpen ? 0 : -12
    transform: Translate { y: launcher.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    // Reset search when closed
    onLauncherOpenChanged: {
        if (!launcherOpen) searchInput.clear();
    }

    // ── Content ────────────────────────────────────────────────────────────
    Column {
        id: contentCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top

        // ── Search bar ──────────────────────────────────────────────────────
        Rectangle {
            width: parent.width
            height: Theme.containerHeight + 16
            color: "transparent"

            Rectangle {
                anchors.fill: parent
                anchors.margins: 8
                radius: Theme.containerRadius
                color: Theme.containerBg

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 8
                    spacing: 8

                    Text {
                        text: "\uf002"
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.textFontSize
                        color: Theme.dotEmpty
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    TextInput {
                        id: searchInput
                        width: parent.width - 52
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                        selectionColor: Theme.dotSelected
                        selectedTextColor: Theme.menuBg

                        Text {
                            anchors.fill: parent
                            text: "Search apps…"
                            color: Theme.dotEmpty
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize
                            visible: searchInput.text.length === 0
                        }
                    }

                    // Clear button
                    Rectangle {
                        width: 20
                        height: 20
                        radius: 10
                        anchors.verticalCenter: parent.verticalCenter
                        color: clearArea.containsMouse ? Theme.menuHover : "transparent"
                        visible: searchInput.text.length > 0

                        Text {
                            anchors.centerIn: parent
                            text: "\uf00d"
                            font.family: Theme.iconFont
                            font.pixelSize: 11
                            color: Theme.dotEmpty
                        }

                        MouseArea {
                            id: clearArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: searchInput.clear()
                        }
                    }
                }
            }
        }

        // ── Thin divider ────────────────────────────────────────────────────
        Rectangle {
            width: parent.width
            height: 1
            color: Theme.menuBorder
        }

        // ── App list ─────────────────────────────────────────────────────────
        ListView {
            id: appList
            width: parent.width
            height: Math.min(contentHeight, Theme.launcherMaxHeight - Theme.containerHeight - 24)
            clip: true

            model: AppService.search(searchInput.text)

            delegate: Item {
                required property var modelData
                width: appList.width
                height: Theme.launcherItemHeight

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 4
                    radius: Theme.containerRadius
                    color: itemArea.containsMouse ? Theme.menuHover : "transparent"
                }

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 6
                    anchors.bottomMargin: 6
                    spacing: 12

                    // App icon
                    IconImage {
                        width: 32
                        height: 32
                        anchors.verticalCenter: parent.verticalCenter
                        source: Quickshell.iconPath(modelData.icon ?? "", "application-x-executable")
                        asynchronous: true
                        mipmap: true
                    }

                    // Name + description
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        width: parent.width - 56

                        Text {
                            text: modelData.name ?? ""
                            color: Theme.textColor
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize
                            elide: Text.ElideRight
                            width: parent.width
                        }

                        Text {
                            text: modelData.comment || modelData.genericName || ""
                            color: Theme.dotEmpty
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize - 2
                            elide: Text.ElideRight
                            width: parent.width
                            visible: text.length > 0
                        }
                    }
                }

                MouseArea {
                    id: itemArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        AppService.launch(modelData);
                        launcher.launcherOpen = false;
                    }
                }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                visible: appList.count === 0 && searchInput.text.length > 0
                text: "No apps found"
                color: Theme.dotEmpty
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize
            }
        }
    }
}
