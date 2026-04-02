import QtQuick
import PyShell.Services 1.0

Item {
    id: root
    anchors.fill: parent

    readonly property int toastWidth: 340
    readonly property int toastSpacing: 8
    readonly property int toastTopMargin: Theme.barHeight + 8
    readonly property int toastRightMargin: Theme.edgeMargin

    Column {
        anchors.top: parent.top
        anchors.topMargin: root.toastTopMargin
        anchors.right: parent.right
        anchors.rightMargin: root.toastRightMargin
        spacing: root.toastSpacing

        Repeater {
            model: Math.min(NotificationService.popupQueue.length, 5)

            delegate: NotificationToast {
                required property int index
                property var capturedNotif: NotificationService.popupQueue[index]
                notif: capturedNotif
                onDone: NotificationService.removeFromQueue(capturedNotif)
            }
        }
    }

    component NotificationToast: Rectangle {
        id: toast

        property var notif
        signal done()

        width: root.toastWidth
        height: toastContent.implicitHeight + 20
        radius: Theme.menuRadius
        color: Theme.menuBg
        border.color: notif && notif.urgency === 2 ? Qt.alpha("#f7768e", 0.5) : Theme.menuBorder
        border.width: 1
        clip: false

        x: root.toastWidth + root.toastRightMargin + 20

        Component.onCompleted: slideInAnim.start()

        NumberAnimation {
            id: slideInAnim
            target: toast
            property: "x"
            to: 0
            duration: 300
            easing.type: Easing.OutCubic
            onStarted: expireTimer.start()
        }

        NumberAnimation {
            id: slideOutAnim
            target: toast
            property: "x"
            to: root.toastWidth + root.toastRightMargin + 20
            duration: 250
            easing.type: Easing.InCubic
            onFinished: toast.done()
        }

        Timer {
            id: expireTimer
            interval: (toast.notif && toast.notif.expireTimeout > 0) ? toast.notif.expireTimeout : 5000
            onTriggered: {
                if (!slideOutAnim.running)
                    slideOutAnim.start()
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            onEntered: expireTimer.stop()
            onExited: {
                if (!slideOutAnim.running)
                    expireTimer.restart()
            }
            onClicked: {
                expireTimer.stop()
                if (!slideOutAnim.running)
                    slideOutAnim.start()
            }
        }

        Column {
            id: toastContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            spacing: 4

            Row {
                width: parent.width
                spacing: 6

                Text {
                    text: (toast.notif && toast.notif.appName) ? toast.notif.appName : "Notification"
                    color: Qt.alpha(Theme.textColor, 0.55)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize - 2
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight
                    width: parent.width - closeBtn.width - 4
                }

                Rectangle {
                    id: closeBtn
                    width: 18; height: 18; radius: 9
                    color: closeBtnArea.containsMouse ? Theme.menuHover : "transparent"
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.centerIn: parent
                        text: "\uf00d"
                        font.family: Theme.iconFont
                        font.pixelSize: 10
                        color: Qt.alpha(Theme.textColor, 0.5)
                    }

                    MouseArea {
                        id: closeBtnArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            expireTimer.stop()
                            if (!slideOutAnim.running)
                                slideOutAnim.start()
                        }
                    }
                }
            }

            Text {
                width: parent.width
                text: (toast.notif && toast.notif.summary) ? toast.notif.summary : ""
                color: Theme.textColor
                font.family: Theme.clockFont
                font.pixelSize: Theme.textFontSize
                font.bold: true
                wrapMode: Text.WordWrap
                visible: text !== ""
            }

            Text {
                width: parent.width
                text: (toast.notif && toast.notif.body) ? toast.notif.body : ""
                color: Qt.alpha(Theme.textColor, 0.75)
                font.family: Theme.monoFont
                font.pixelSize: Theme.textFontSize - 1
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                visible: text !== ""
            }
        }
    }
}
