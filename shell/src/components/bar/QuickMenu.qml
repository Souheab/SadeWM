import QtQuick
import PyShell.Services 1.0
import "../shared"

Rectangle {
    id: configMenu

    property Item popupLayer: null
    property bool menuOpen: false
    property real anchorX: 0
    property real anchorY: 0

    property bool powerExpanded: false
    property bool confirmOpen: false
    property string pendingAction: ""
    property string pendingLabel: ""
    property string pendingIcon: ""
    property color  pendingColor: Theme.dangerColor

    signal closeRequested()

    parent: configMenu.popupLayer
    visible: opacity > 0
    opacity: configMenu.menuOpen ? 1.0 : 0.0
    x: configMenu.anchorX
    y: configMenu.anchorY

    width: Theme.menuWidth
    height: menuColumn.implicitHeight

    color: Theme.menuBg
    radius: Theme.menuRadius
    border.color: Theme.menuBorder
    border.width: 1

    onHeightChanged: if (configMenu.menuOpen && configMenu.popupLayer)
        Qt.callLater(configMenu.popupLayer.updateInputRegion)
    onVisibleChanged: if (configMenu.popupLayer)
        Qt.callLater(configMenu.popupLayer.updateInputRegion)

    property real slideOffset: configMenu.menuOpen ? 0 : -12
    transform: Translate { y: configMenu.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    onMenuOpenChanged: {
        if (!menuOpen) {
            powerExpanded = false
            confirmOpen = false
        }
    }

    function launch(cmd) {
        AppService.launchCommand(cmd);
        configMenu.closeRequested();
    }

    Column {
        id: menuColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        topPadding: 6
        bottomPadding: 6

        Repeater {
            model: [
                { label: "NixOS Config",      icon: "\uf313", cmd: ["wezterm", "start", "--", "nvim", "/home/suller/Documents/nixos/flake.nix"],    color: "#7aa2f7", sep: false },
                { label: "Quickshell Config", icon: "\uf120", cmd: ["wezterm", "start", "--", "nvim", "/home/suller/.config/quickshell/shell.qml"], color: "#bb9af7", sep: true  },
                { label: "Terminal",          icon: "\uf489", cmd: ["wezterm", "start"],                                        color: "#7dcfff", sep: false },
                { label: "Files",             icon: "\uf413", cmd: ["wezterm", "start", "--", "yazi"],                         color: "#e0af68", sep: false },
                { label: "Firefox",           icon: "\uf269", cmd: ["firefox"],                                                 color: "#ff9e64", sep: true  }
            ]

            Item {
                required property var modelData
                width: menuColumn.width
                height: Theme.menuItemHeight + (modelData.sep ? 9 : 0)

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

                        Item {
                            width: 16
                            height: parent.height

                            Text {
                                anchors.centerIn: parent
                                text: modelData.icon
                                color: itemArea.containsMouse ? modelData.color : Qt.alpha(Theme.textColor, 0.55)
                                font.family: Theme.iconFont
                                font.pixelSize: 13
                            }
                        }

                        Text {
                            text: modelData.label
                            color: itemArea.containsMouse ? Theme.textColor : Qt.alpha(Theme.textColor, 0.82)
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

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
                    cursorShape: Qt.PointingHandCursor
                    onClicked: configMenu.launch(modelData.cmd)
                }
            }
        }

        // Power toggle row
        Item {
            width: menuColumn.width
            height: Theme.menuItemHeight

            Rectangle {
                x: 5; y: 2
                width: parent.width - 10
                height: Theme.menuItemHeight - 4
                radius: Theme.containerRadius - 2
                color: powerToggleArea.containsMouse ? Theme.menuHover : "transparent"

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    spacing: 10

                    Item {
                        width: 16
                        height: parent.height

                        Text {
                            anchors.centerIn: parent
                            text: "\uf011"
                            color: powerToggleArea.containsMouse ? Theme.dangerColor : Qt.alpha(Theme.textColor, 0.55)
                            font.family: Theme.iconFont
                            font.pixelSize: 13
                        }
                    }

                    Text {
                        text: "Power"
                        color: powerToggleArea.containsMouse ? Theme.textColor : Qt.alpha(Theme.textColor, 0.82)
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: configMenu.powerExpanded ? "\uf078" : "\uf054"
                    font.family: Theme.iconFont
                    font.pixelSize: 10
                    color: Qt.alpha(Theme.textColor, 0.4)
                }
            }

            MouseArea {
                id: powerToggleArea
                x: 5; y: 2
                width: parent.width - 10
                height: Theme.menuItemHeight - 4
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    configMenu.confirmOpen = false
                    configMenu.powerExpanded = !configMenu.powerExpanded
                }
            }
        }

        // Power submenu (expandable)
        Item {
            width: menuColumn.width
            height: configMenu.powerExpanded ? powerSubCol.implicitHeight : 0
            clip: true

            Behavior on height {
                NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }

            Column {
                id: powerSubCol
                anchors.left: parent.left
                anchors.right: parent.right

                Repeater {
                    model: [
                        { label: "Lock",     icon: "\uf023", cmd: "lock",     color: "#7aa2f7" },
                        { label: "Suspend",  icon: "\uf186", cmd: "suspend",  color: "#bb9af7" },
                        { label: "Reboot",   icon: "\uf021", cmd: "reboot",   color: "#e0af68" },
                        { label: "Shutdown", icon: "\uf011", cmd: "shutdown", color: "#f7768e" },
                        { label: "Log Out",  icon: "\uf2f5", cmd: "logout",   color: "#7dcfff" }
                    ]

                    Item {
                        required property var modelData
                        width: powerSubCol.width
                        height: Theme.menuItemHeight - 4

                        Rectangle {
                            x: 10; y: 2
                            width: parent.width - 20
                            height: parent.height - 4
                            radius: Theme.containerRadius - 2
                            color: subArea.containsMouse ? Theme.menuHover : "transparent"

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                spacing: 10

                                Item {
                                    width: 16
                                    height: parent.height

                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.icon
                                        color: subArea.containsMouse ? modelData.color : Qt.alpha(Theme.textColor, 0.55)
                                        font.family: Theme.iconFont
                                        font.pixelSize: 12
                                    }
                                }

                                Text {
                                    text: modelData.label
                                    color: subArea.containsMouse ? Theme.textColor : Qt.alpha(Theme.textColor, 0.75)
                                    font.family: Theme.monoFont
                                    font.pixelSize: Theme.textFontSize - 1
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }

                        MouseArea {
                            id: subArea
                            x: 10; y: 2
                            width: parent.width - 20
                            height: parent.height - 4
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                configMenu.pendingAction = modelData.cmd
                                configMenu.pendingLabel  = modelData.label
                                configMenu.pendingIcon   = modelData.icon
                                configMenu.pendingColor  = modelData.color
                                configMenu.confirmOpen   = true
                                configMenu.powerExpanded = false
                            }
                        }
                    }
                }
            }
        }

        // Inline confirm dialog
        Item {
            width: menuColumn.width
            height: configMenu.confirmOpen ? confirmCol.implicitHeight + 20 : 0
            clip: true

            Behavior on height {
                NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }

            Column {
                id: confirmCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 14
                anchors.topMargin: 12
                spacing: 10

                Rectangle {
                    width: 44
                    height: 44
                    radius: 22
                    color: Qt.alpha(configMenu.pendingColor, 0.15)
                    anchors.horizontalCenter: parent.horizontalCenter

                    Text {
                        anchors.centerIn: parent
                        text: configMenu.pendingIcon
                        color: configMenu.pendingColor
                        font.family: Theme.iconFont
                        font.pixelSize: 18
                    }
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: configMenu.pendingLabel
                    color: Theme.textColor
                    font.family: Theme.clockFont
                    font.pixelSize: Theme.textFontSize + 2
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Are you sure?"
                    color: Qt.alpha(Theme.textColor, 0.4)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 1
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Theme.spacingSM

                    Rectangle {
                        width: 88; height: 30
                        radius: Theme.containerRadius
                        color: cfCancelArea.containsMouse ? Theme.menuHover : "transparent"
                        border.color: Qt.alpha(Theme.textColor, 0.18)
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "Cancel"
                            color: Qt.alpha(Theme.textColor, 0.65)
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize - 1
                        }

                        MouseArea {
                            id: cfCancelArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: configMenu.confirmOpen = false
                        }
                    }

                    Rectangle {
                        width: 88; height: 30
                        radius: Theme.containerRadius
                        color: cfConfirmArea.containsMouse
                            ? Qt.darker(configMenu.pendingColor, 1.18)
                            : configMenu.pendingColor

                        Text {
                            anchors.centerIn: parent
                            text: configMenu.pendingLabel
                            color: "#1a1b26"
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize - 1
                            font.weight: Font.Medium
                        }

                        MouseArea {
                            id: cfConfirmArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                configMenu.confirmOpen = false
                                configMenu.closeRequested()
                                PowerService.execute(configMenu.pendingAction)
                            }
                        }
                    }
                }

                Item { width: 1; height: 2 }
            }
        }
    }
}
