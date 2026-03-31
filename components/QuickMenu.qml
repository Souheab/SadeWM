import QtQuick
import Quickshell
import Quickshell.Io
import ".."

// Quick-launch menu — configs, apps, and utilities.
// Reparented to the popup layer, same pattern as PowerMenu.
Rectangle {
    id: configMenu

    property Item popupLayer: null
    property bool menuOpen: false
    property real anchorX: 0
    property real anchorY: 0

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

    property real slideOffset: configMenu.menuOpen ? 0 : -12
    transform: Translate { y: configMenu.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    Process {
        id: runCmd
        property var pendingCmd: []
        command: runCmd.pendingCmd
        onRunningChanged: {
            if (!running)
                runCmd.pendingCmd = [];
        }
    }

    function launch(cmd) {
        runCmd.pendingCmd = cmd;
        runCmd.running = true;
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
                { label: "Firefox",           icon: "\uf269", cmd: ["firefox"],                                                 color: "#ff9e64", sep: false }
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
    }
}
