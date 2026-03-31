import QtQuick
import Quickshell
import Quickshell.Io
import ".."
import "../services"

// Power button in the bar. Popups render as siblings in the same PanelWindow.
Rectangle {
    id: powerButton
    width: Theme.containerHeight
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: buttonArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool menuOpen: false
    property bool confirmOpen: false
    property string pendingAction: ""
    property string pendingLabel: ""
    property string pendingIcon: ""
    property color  pendingColor: Theme.dangerColor

    // Screen-space position for popups (relative to the PanelWindow root)
    property real popupX: 0
    property real popupY: 0

    // Find the popup layer to control visibility and position popups
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

    function updatePopupPosition() {
        if (!popupLayer) return;
        const pos = powerButton.mapToItem(popupLayer, powerButton.width, powerButton.height);
        popupX = pos.x - Theme.menuWidth;
        popupY = pos.y + 4;
    }

    onMenuOpenChanged: if (popupLayer) popupLayer.popupVisible = menuOpen || confirmOpen
    onConfirmOpenChanged: if (popupLayer) popupLayer.popupVisible = menuOpen || confirmOpen

    // Close popups when the overlay is dismissed (click outside)
    Connections {
        target: powerButton.popupLayer
        function onPopupVisibleChanged() {
            if (powerButton.popupLayer && !powerButton.popupLayer.popupVisible) {
                powerButton.menuOpen = false;
                powerButton.confirmOpen = false;
            }
        }
    }

    Text {
        anchors.centerIn: parent
        text: "\uf011"
        color: buttonArea.containsMouse ? Theme.dangerColor : Qt.alpha(Theme.textColor, 0.8)
        font.family: Theme.iconFont
        font.pixelSize: Theme.iconFontSize
        Behavior on color { ColorAnimation { duration: 150 } }
    }

    MouseArea {
        id: buttonArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
            if (powerButton.menuOpen) {
                powerButton.menuOpen = false;
            } else {
                powerButton.updatePopupPosition();
                powerButton.confirmOpen = false;
                powerButton.menuOpen = true;
            }
        }
    }

    // ── Dropdown menu ─────────────────────────────────────────────────────────
    Rectangle {
        id: menuPopup
        parent: powerButton.popupLayer
        visible: opacity > 0
        opacity: powerButton.menuOpen ? 1.0 : 0.0
        x: powerButton.popupX
        y: powerButton.popupY
        width: Theme.menuWidth
        height: menuColumn.implicitHeight
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        property real slideOffset: powerButton.menuOpen ? 0 : -12
        transform: Translate { y: menuPopup.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Column {
            id: menuColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            topPadding: 6
            bottomPadding: 6

            Repeater {
                model: [
                    { label: "Lock",     icon: "\uf023", cmd: "lock",     color: "#7aa2f7", sep: false },
                    { label: "Suspend",  icon: "\uf186", cmd: "suspend",  color: "#bb9af7", sep: true  },
                    { label: "Reboot",   icon: "\uf021", cmd: "reboot",   color: "#e0af68", sep: false },
                    { label: "Shutdown", icon: "\uf011", cmd: "shutdown", color: "#f7768e", sep: false },
                    { label: "Log Out",  icon: "\uf2f5", cmd: "logout",   color: "#7dcfff", sep: false }
                ]

                Item {
                    required property var modelData
                    required property int index
                    width: menuColumn.width
                    // Extra height for the separator gap after the item
                    height: Theme.menuItemHeight + (modelData.sep ? 9 : 0)

                    // Item background
                    Rectangle {
                        x: 5; y: 2
                        width: parent.width - 10
                        height: Theme.menuItemHeight - 4
                        radius: Theme.containerRadius - 2
                        color: itemArea.containsMouse ? Theme.menuHover : "transparent"

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            spacing: 10

                            // Icon column — fixed width for alignment
                            Item {
                                width: 16
                                height: parent.height

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.icon
                                    color: itemArea.containsMouse ? modelData.color : Qt.alpha(Theme.textColor, 0.55)
                                    font.family: Theme.iconFont
                                    font.pixelSize: 13
                                    Behavior on color { ColorAnimation { duration: 150 } }
                                }
                            }

                            Text {
                                text: modelData.label
                                color: itemArea.containsMouse ? Theme.textColor : Qt.alpha(Theme.textColor, 0.82)
                                font.family: Theme.monoFont
                                font.pixelSize: Theme.textFontSize
                                anchors.verticalCenter: parent.verticalCenter
                                Behavior on color { ColorAnimation { duration: 150 } }
                            }
                        }
                    }

                    // Thin divider drawn below items where sep:true
                    Rectangle {
                        visible: modelData.sep
                        x: 14
                        y: Theme.menuItemHeight + 2
                        width: parent.width - 28
                        height: 1
                        color: Qt.alpha(Theme.menuBorder, 0.8)
                    }

                    MouseArea {
                        id: itemArea
                        x: 5; y: 2
                        width: parent.width - 10
                        height: Theme.menuItemHeight - 4
                        hoverEnabled: true
                        onClicked: {
                            powerButton.pendingAction = modelData.cmd;
                            powerButton.pendingLabel  = modelData.label;
                            powerButton.pendingIcon   = modelData.icon;
                            powerButton.pendingColor  = modelData.color;
                            powerButton.menuOpen      = false;
                            powerButton.confirmOpen   = true;
                        }
                    }
                }
            }
        }
    }

    // ── Confirmation dialog ───────────────────────────────────────────────────
    Rectangle {
        id: confirmPopup
        parent: powerButton.popupLayer
        visible: opacity > 0
        opacity: powerButton.confirmOpen ? 1.0 : 0.0
        x: powerButton.popupX + Theme.menuWidth - Theme.confirmDialogWidth
        y: powerButton.popupY
        width: Theme.confirmDialogWidth
        height: confirmContent.implicitHeight + 40
        color: Theme.confirmBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        property real slideOffset: powerButton.confirmOpen ? 0 : -12
        transform: Translate { y: confirmPopup.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Column {
            id: confirmContent
            anchors.centerIn: parent
            width: parent.width - 40
            spacing: 12

            // Large colored icon circle
            Rectangle {
                width: 52
                height: 52
                radius: 26
                color: Qt.alpha(powerButton.pendingColor, 0.15)
                anchors.horizontalCenter: parent.horizontalCenter

                Text {
                    anchors.centerIn: parent
                    text: powerButton.pendingIcon
                    color: powerButton.pendingColor
                    font.family: Theme.iconFont
                    font.pixelSize: 22
                }
            }

            // Action name
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: powerButton.pendingLabel
                color: Theme.textColor
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize + 3
            }

            // Subtext
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Are you sure?"
                color: Qt.alpha(Theme.textColor, 0.4)
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize - 1
            }

            // Buttons
            Item { width: 1; height: 2 }  // small extra gap before buttons

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.spacingSM

                // Cancel — outline style
                Rectangle {
                    width: 104
                    height: 34
                    radius: Theme.containerRadius
                    color: cancelArea.containsMouse ? Theme.menuHover : "transparent"
                    border.color: Qt.alpha(Theme.textColor, 0.18)
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: Qt.alpha(Theme.textColor, 0.65)
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                    }

                    MouseArea {
                        id: cancelArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: powerButton.confirmOpen = false
                    }
                }

                // Confirm — solid action color
                Rectangle {
                    width: 104
                    height: 34
                    radius: Theme.containerRadius
                    color: confirmArea.containsMouse
                        ? Qt.darker(powerButton.pendingColor, 1.18)
                        : powerButton.pendingColor
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Text {
                        anchors.centerIn: parent
                        text: powerButton.pendingLabel
                        color: "#1a1b26"
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                        font.weight: Font.Medium
                    }

                    MouseArea {
                        id: confirmArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            powerButton.confirmOpen = false;
                            execProcess.command = ["python3", Qt.resolvedUrl("../scripts/qsctrl").toString().replace("file://", ""), "power", powerButton.pendingAction];
                            execProcess.running = true;
                        }
                    }
                }
            }
        }
    }

    Process {
        id: execProcess
    }
}

