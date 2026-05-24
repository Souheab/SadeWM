import QtQuick
import QtQuick.Window
import "../shared"
import PyShell.Services 1.0

Window {
    id: dialog

    visible: false
    color: "#99000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    property string errorText: ""

    function open() {
        errorText = ""
        dialog.visible = true
        dialog.raise()
        dialog.requestActivate()
        focusTimer.start()
    }

    function close() {
        dialog.visible = false
        errorText = ""
    }

    function confirmExit() {
        if (WMIPCService.quit()) {
            dialog.close()
        } else {
            errorText = WMIPCService.error
        }
    }

    Timer {
        id: focusTimer
        interval: 50
        repeat: false
        onTriggered: {
            dialog.requestActivate()
            cancelButton.forceActiveFocus()
            WindowHelper.grabKeyboard(dialog)
        }
    }

    Connections {
        target: IPCService
        function onConfirmExitRequested() {
            if (dialog.visible)
                dialog.close()
            else
                dialog.open()
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: dialog.close()
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            dialog.close()
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            dialog.confirmExit()
            event.accepted = true
        }
    }

    Rectangle {
        id: card
        width: Math.min(360, parent.width * 0.9)
        height: content.implicitHeight + 40
        anchors.centerIn: parent
        color: Theme.barBg
        radius: 12
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        MouseArea { anchors.fill: parent }

        Column {
            id: content
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: 24
            spacing: 14

            Rectangle {
                width: 48
                height: 48
                radius: 24
                color: Qt.alpha(Theme.dangerColor, 0.15)
                anchors.horizontalCenter: parent.horizontalCenter

                Text {
                    anchors.centerIn: parent
                    text: "\uf011"
                    color: Theme.dangerColor
                    font.family: Theme.iconFont
                    font.pixelSize: 20
                }
            }

            Text {
                width: parent.width
                text: "Exit sadewm?"
                color: Theme.textColor
                horizontalAlignment: Text.AlignHCenter
                font.family: Theme.clockFont
                font.pixelSize: 18
                font.weight: Font.Medium
            }

            Text {
                width: parent.width
                text: "This will close the window manager."
                color: Qt.alpha(Theme.textColor, 0.55)
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize
            }

            Text {
                width: parent.width
                visible: dialog.errorText.length > 0
                text: dialog.errorText
                color: Theme.dangerColor
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize - 1
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.spacingSM

                Rectangle {
                    id: cancelButton
                    width: 104
                    height: 34
                    radius: 8
                    color: cancelArea.containsMouse ? Theme.menuHover : "transparent"
                    border.color: Qt.alpha(Theme.textColor, 0.18)
                    border.width: 1
                    focus: true

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: Qt.alpha(Theme.textColor, 0.72)
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                    }

                    MouseArea {
                        id: cancelArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dialog.close()
                    }
                }

                Rectangle {
                    width: 104
                    height: 34
                    radius: 8
                    color: confirmArea.containsMouse ? Qt.darker(Theme.dangerColor, 1.18) : Theme.dangerColor

                    Text {
                        anchors.centerIn: parent
                        text: "Exit"
                        color: Theme.barBg
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                        font.weight: Font.Medium
                    }

                    MouseArea {
                        id: confirmArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dialog.confirmExit()
                    }
                }
            }
        }
    }
}
