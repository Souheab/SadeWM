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
        color: Theme.textColor
        font.family: Theme.iconFont
        font.pixelSize: Theme.iconFontSize
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

    // Dropdown menu — reparented to the popup layer
    Rectangle {
        id: menuPopup
        parent: powerButton.popupLayer
        visible: opacity > 0
        opacity: powerButton.menuOpen ? 1.0 : 0.0
        x: powerButton.popupX
        y: powerButton.popupY
        width: Theme.menuWidth
        height: menuColumn.height + 12
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
            anchors.margins: 6

            Repeater {
                model: [
                    { label: "Lock",     icon: "\uf023", cmd: "lock"     },
                    { label: "Suspend",  icon: "\uf186", cmd: "suspend"  },
                    { label: "Reboot",   icon: "\uf021", cmd: "reboot"   },
                    { label: "Shutdown", icon: "\uf011", cmd: "shutdown" },
                    { label: "Log Out",  icon: "\uf2f5", cmd: "logout"   }
                ]

                Rectangle {
                    required property var modelData
                    required property int index
                    width: menuColumn.width
                    height: Theme.menuItemHeight
                    radius: Theme.containerRadius
                    color: itemArea.containsMouse ? Theme.menuHover : "transparent"

                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 8

                        Text {
                            text: modelData.icon
                            font.family: Theme.iconFont
                            font.pixelSize: Theme.iconFontSize
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: modelData.label
                            color: Theme.textColor
                            font.pixelSize: Theme.textFontSize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    MouseArea {
                        id: itemArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            powerButton.pendingAction = modelData.cmd;
                            powerButton.pendingLabel = modelData.label;
                            powerButton.menuOpen = false;
                            powerButton.confirmOpen = true;
                        }
                    }
                }
            }
        }
    }

    // Confirmation dialog — reparented to the popup layer
    Rectangle {
        id: confirmPopup
        parent: powerButton.popupLayer
        visible: opacity > 0
        opacity: powerButton.confirmOpen ? 1.0 : 0.0
        x: powerButton.popupX + Theme.menuWidth - Theme.confirmDialogWidth
        y: powerButton.popupY
        width: Theme.confirmDialogWidth
        height: 128
        color: Theme.confirmBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        property real slideOffset: powerButton.confirmOpen ? 0 : -12
        transform: Translate { y: confirmPopup.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

        Column {
            anchors.centerIn: parent
            spacing: 16

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: powerButton.pendingLabel + "?"
                color: Theme.textColor
                font.pixelSize: Theme.textFontSize
                font.family: Theme.clockFont
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                Rectangle {
                    width: 100
                    height: 34
                    radius: Theme.containerRadius
                    color: cancelArea.containsMouse ? Theme.menuHover : Theme.containerBg

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: Theme.textColor
                        font.pixelSize: Theme.textFontSize
                    }

                    MouseArea {
                        id: cancelArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: powerButton.confirmOpen = false
                    }
                }

                Rectangle {
                    width: 100
                    height: 34
                    radius: Theme.containerRadius
                    color: confirmArea.containsMouse ? Qt.darker(Theme.dangerColor, 1.2) : Theme.dangerColor

                    Text {
                        anchors.centerIn: parent
                        text: "Confirm"
                        color: "#ffffff"
                        font.pixelSize: Theme.textFontSize
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
