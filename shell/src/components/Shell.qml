import QtQuick
import QtQuick.Window
import PyShell.Services 1.0

Window {
    id: root

    visible: false  // Don't show until after we set position
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

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

                    NotificationButton {
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    SystrayWidget {
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

        // Build the X11 input-shape rect list and push it to WindowHelper.
        // Only areas where real UI is rendered will capture pointer events;
        // everything else passes through to windows below so the WM's
        // focus-follows-mouse keeps working.
        function updateInputRegion() {
            var rects = [{x: 0, y: 0, width: Screen.width, height: Theme.barHeight}]

            // Panel popups are reparented into popupLayer at runtime.
            // Iterate children and collect every visible, non-full-screen item.
            for (var i = 0; i < children.length; i++) {
                var c = children[i]
                if (c === notifPopups) continue   // handled separately below
                if (!c.visible) continue
                if (c.width <= 0 || c.height <= 0) continue
                rects.push({
                    x: Math.round(c.x), y: Math.round(c.y),
                    width: Math.round(c.width), height: Math.round(c.height)
                })
            }

            // Toast notifications: the overlay Item is full-screen, so we
            // derive the actual column bounding rect from notifPopups.
            if (toastsActive && notifPopups.toastAreaRect.height > 0) {
                var tr = notifPopups.toastAreaRect
                rects.push({
                    x: Math.round(tr.x), y: Math.round(tr.y),
                    width: Math.round(tr.width), height: Math.round(tr.height)
                })
            }

            WindowHelper.setInputRegion(rects)
        }

        onPopupVisibleChanged: {
            if (popupVisible || mediaVisible) {
                maskCollapseTimer.stop();
                maskActive = true;
            } else {
                maskCollapseTimer.restart();
            }
            Qt.callLater(updateInputRegion)
        }

        onMediaVisibleChanged: {
            if (popupVisible || mediaVisible) {
                maskCollapseTimer.stop();
                maskActive = true;
            } else {
                maskCollapseTimer.restart();
            }
            Qt.callLater(updateInputRegion)
        }

        onToastsActiveChanged: Qt.callLater(updateInputRegion)
        onMaskActiveChanged:   Qt.callLater(updateInputRegion)

        // Keep input region in sync when the media card or toast column resizes.
        Connections {
            target: mediaPopup
            function onHeightChanged() { Qt.callLater(popupLayer.updateInputRegion) }
        }
        Connections {
            target: notifPopups
            function onToastAreaRectChanged() { Qt.callLater(popupLayer.updateInputRegion) }
        }

        MediaDetails {
            id: mediaPopup
            popupLayer: popupLayer
            menuOpen: popupLayer.mediaVisible
            anchorX: (root.width - Theme.mediaCardWidth) / 2
            anchorY: Theme.barHeight + 4
            onCloseRequested: popupLayer.mediaVisible = false
        }

        NotificationPopups { id: notifPopups }

        Timer {
            id: maskCollapseTimer
            interval: Theme.popupAnimDuration
            onTriggered: popupLayer.maskActive = (popupLayer.popupVisible || popupLayer.mediaVisible)
        }
    }

    // Set X11 window properties and show after window is ready.
    Component.onCompleted: {
        // Ensure position is set before showing
        root.x = 0;
        root.y = 0;
        // Set up X11 properties (EWMH dock hints, positioning, etc.)
        WindowHelper.setupX11(root);
        // Now show the window
        root.visible = true;
        Qt.callLater(popupLayer.updateInputRegion);
    }

    // Safety net: if winId wasn't ready at onCompleted, re-run once the
    // window becomes truly visible (native surface created).
    onVisibleChanged: {
        if (visible) {
            WindowHelper.setupX11(root);
            Qt.callLater(popupLayer.updateInputRegion);
        }
    }
}
