import QtQuick
import PyShell.Services 1.0
import "../shared"

Item {
    id: root
    anchors.fill: parent

    readonly property int toastWidth: 340
    readonly property int toastSpacing: 8
    readonly property int toastTopMargin: Theme.barHeight + 8
    readonly property int toastRightMargin: Theme.edgeMargin

    signal inputRegionChanged()

    // Return only toast rectangles that are both on-screen and ready for input.
    // In particular, an expired toast that has slid off-screen must not leave a
    // transparent input rectangle behind.
    function inputRects() {
        var rects = []
        for (var i = 0; i < toastColumn.children.length; i++) {
            var toast = toastColumn.children[i]
            if (!toast.visible || !toast.inputActive)
                continue

            var pos = toast.mapToItem(root, 0, 0)
            var left = Math.max(0, Math.round(pos.x))
            var top = Math.max(0, Math.round(pos.y))
            var right = Math.min(root.width, Math.round(pos.x + toast.width))
            var bottom = Math.min(root.height, Math.round(pos.y + toast.height))
            if (right > left && bottom > top) {
                rects.push({
                    x: left, y: top,
                    width: right - left, height: bottom - top
                })
            }
        }
        return rects
    }

    Column {
        id: toastColumn
        anchors.top: parent.top
        anchors.topMargin: root.toastTopMargin
        anchors.right: parent.right
        anchors.rightMargin: root.toastRightMargin
        spacing: root.toastSpacing

        Repeater {
            model: NotificationService.popupModel

            delegate: NotificationToast {}
        }
    }

    component NotificationToast: Rectangle {
        id: toast

        required property int index
        required property var notification
        readonly property var notif: notification
        property bool inputActive: false

        width: root.toastWidth
        height: toastContent.implicitHeight + 20
        visible: index < 5
        radius: Theme.menuRadius
        color: Theme.menuBg
        border.color: notif && notif.urgency === 2 ? Qt.alpha("#f7768e", 0.5) : Theme.menuBorder
        border.width: 1
        clip: false

        x: root.toastWidth + root.toastRightMargin + 20

        function beginShowing() {
            if (!toast.visible || slideInAnim.running || toast.inputActive)
                return
            slideOutAnim.stop()
            expireTimer.stop()
            toast.x = root.toastWidth + root.toastRightMargin + 20
            slideInAnim.restart()
        }

        Component.onCompleted: Qt.callLater(beginShowing)
        Component.onDestruction: root.inputRegionChanged()
        onVisibleChanged: {
            if (visible) {
                Qt.callLater(beginShowing)
            } else {
                slideInAnim.stop()
                slideOutAnim.stop()
                expireTimer.stop()
                inputActive = false
                x = root.toastWidth + root.toastRightMargin + 20
                root.inputRegionChanged()
            }
        }
        onHeightChanged: if (inputActive) root.inputRegionChanged()

        NumberAnimation {
            id: slideInAnim
            target: toast
            property: "x"
            to: 0
            duration: 300
            easing.type: Easing.OutCubic
            onStarted: {
                toast.inputActive = false
                root.inputRegionChanged()
            }
            onFinished: {
                toast.inputActive = true
                root.inputRegionChanged()
                expireTimer.start()
            }
        }

        NumberAnimation {
            id: slideOutAnim
            target: toast
            property: "x"
            to: root.toastWidth + root.toastRightMargin + 20
            duration: 250
            easing.type: Easing.InCubic
            onStarted: {
                toast.inputActive = false
                root.inputRegionChanged()
            }
            onFinished: NotificationService.removeFromQueueById(toast.notif.id)
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
