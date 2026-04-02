import QtQuick
import QtQuick.Window
import PyShell.Services 1.0

Window {
    id: root

    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    // The bar is drawn at the top; popups render below.
    // When no popup is open, only the bar strip is interactive.

    Rectangle {
        id: barArea
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.barHeight
        color: Theme.barBg

        Row {
            anchors.fill: parent
            spacing: 0

            // Left section - Workspace dots
            Item {
                width: parent.width * 0.33
                height: parent.height

                WorkspaceDots {
                    anchors.verticalCenter: parent.verticalCenter
                    x: Theme.edgeMargin
                }
            }

            // Center section
            Item {
                width: parent.width * 0.34
                height: parent.height

                DateTimeWidget {
                    anchors.centerIn: parent
                }
            }

            // Right section
            Item {
                width: parent.width * 0.33
                height: parent.height

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.edgeMargin
                    spacing: Theme.spacingSM
                    layoutDirection: Qt.RightToLeft

                    SettingsButton {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    NetworkWidget {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    BrightnessWidget {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    AudioWidget {
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }
    }

    // Click-outside-to-close: covers area below the bar
    MouseArea {
        anchors.top: barArea.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: popupLayer.maskActive
        onClicked: {
            popupLayer.popupVisible = false;
            popupLayer.mediaVisible = false;
        }
    }

    // Make the area below the bar click-through when no popups are active.
    // We achieve this via the visible property on the MouseArea above:
    // when maskActive is false, the MouseArea is hidden so clicks pass through.

    Item {
        id: popupLayer
        objectName: "popupLayer"
        property bool popupVisible: false
        property bool mediaVisible: false
        property bool toastsActive: NotificationService.popupQueue.length > 0
        property bool maskActive: false
        anchors.fill: parent

        onPopupVisibleChanged: {
            if (popupVisible || mediaVisible) {
                maskCollapseTimer.stop();
                maskActive = true;
            } else {
                maskCollapseTimer.restart();
            }
        }

        onMediaVisibleChanged: {
            if (popupVisible || mediaVisible) {
                maskCollapseTimer.stop();
                maskActive = true;
            } else {
                maskCollapseTimer.restart();
            }
        }

        MediaDetails {
            id: mediaPopup
            popupLayer: popupLayer
            menuOpen: popupLayer.mediaVisible
            anchorX: (root.width - Theme.mediaCardWidth) / 2
            anchorY: Theme.barHeight + 4
            onCloseRequested: popupLayer.mediaVisible = false
        }

        NotificationPopups {}

        Timer {
            id: maskCollapseTimer
            interval: Theme.popupAnimDuration
            onTriggered: popupLayer.maskActive = (popupLayer.popupVisible || popupLayer.mediaVisible)
        }
    }

    // Set X11 window properties after the window is shown
    Component.onCompleted: {
        WindowHelper.setupX11(root);
    }
}
