import QtQuick
import QtQuick.Window
import "../shared"
import PyShell.Services 1.0

Window {
    id: overlay

    visible: false
    color: "#cc000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    property var keybinds: []

    function open() {
        KeybindService.refresh()
        overlay.visible = true
        overlay.raise()
        overlay.requestActivate()
        focusTimer.start()
    }

    function close() {
        overlay.visible = false
    }

    function chordText(entry) {
        var parts = []
        if (entry.mod) {
            for (var i = 0; i < entry.mod.length; i++)
                parts.push(entry.mod[i])
        }
        parts.push(entry.key || "")
        return parts.join("+")
    }

    Timer {
        id: focusTimer
        interval: 50
        repeat: false
        onTriggered: {
            overlay.requestActivate()
            keyLayer.forceActiveFocus()
            WindowHelper.grabKeyboard(overlay)
        }
    }

    Connections {
        target: IPCService
        function onOpenKeybindsRequested() {
            if (overlay.visible)
                overlay.close()
            else
                overlay.open()
        }
    }

    Connections {
        target: KeybindService
        function onKeybindsChanged() {
            overlay.keybinds = KeybindService.keybinds
        }
    }

    Item {
        id: keyLayer
        anchors.fill: parent
        focus: true

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Escape) {
                overlay.close()
                event.accepted = true
            } else if (event.key === Qt.Key_S && (event.modifiers & Qt.MetaModifier)) {
                overlay.close()
                event.accepted = true
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: overlay.close()
        }

        Rectangle {
            id: panel
            width: Math.min(860, parent.width * 0.92)
            height: Math.min(620, parent.height * 0.84)
            anchors.centerIn: parent
            color: Theme.barBg
            radius: 12
            border.color: Theme.menuBorder
            border.width: 1
            clip: true

            MouseArea { anchors.fill: parent }

            Item {
                id: header
                width: parent.width
                height: 64

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 24
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Keybinds"
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 18
                    font.bold: true
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 24
                    anchors.verticalCenter: parent.verticalCenter
                    text: overlay.keybinds.length + " active"
                    color: Theme.dotOccupied
                    font.family: Theme.monoFont
                    font.pixelSize: 12
                }
            }

            Rectangle {
                id: separator
                anchors.top: header.bottom
                width: parent.width
                height: 1
                color: Theme.menuBorder
            }

            Item {
                id: listArea
                anchors.top: separator.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                clip: true

                Text {
                    id: errorText
                    anchors.centerIn: parent
                    visible: KeybindService.error.length > 0
                    text: KeybindService.error
                    color: Theme.dotUrgent
                    font.family: Theme.monoFont
                    font.pixelSize: 13
                    width: parent.width - 48
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }

                Text {
                    anchors.centerIn: parent
                    visible: KeybindService.error.length === 0 && keybindList.count === 0
                    text: "No keybinds found"
                    color: Theme.dotOccupied
                    font.family: Theme.monoFont
                    font.pixelSize: 13
                }

                ListView {
                    id: keybindList
                    anchors.fill: parent
                    anchors.margins: 14
                    model: overlay.keybinds
                    clip: true
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds
                    visible: KeybindService.error.length === 0

                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: keybindList.width
                        height: 42
                        radius: 6
                        color: index % 2 === 0 ? Qt.rgba(1, 1, 1, 0.025) : "transparent"

                        Text {
                            id: chord
                            anchors.left: parent.left
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(260, parent.width * 0.38)
                            text: overlay.chordText(modelData)
                            color: Theme.dotSelected
                            font.family: Theme.monoFont
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Text {
                            anchors.left: chord.right
                            anchors.leftMargin: 18
                            anchors.right: parent.right
                            anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.description || modelData.action || ""
                            color: Theme.textColor
                            font.family: Theme.monoFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: 5
                    y: 14 + keybindList.visibleArea.yPosition * Math.max(1, keybindList.height - 28)
                    width: 4
                    height: Math.max(32, keybindList.visibleArea.heightRatio * Math.max(1, keybindList.height - 28))
                    radius: 2
                    color: Theme.dotOccupied
                    opacity: keybindList.count > 0 && keybindList.visibleArea.heightRatio < 1 ? 0.7 : 0
                }
            }
        }
    }
}
