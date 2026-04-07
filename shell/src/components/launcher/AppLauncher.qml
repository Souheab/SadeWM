import QtQuick
import QtQuick.Window
import "../shared"
import PyShell.Services 1.0

Window {
    id: launcher

    visible: false
    color: "#80000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    property var filteredApps: []
    property int selectedIndex: 0

    function open() {
        filteredApps = AppService.search("")
        selectedIndex = 0
        searchBox.clear()
        launcher.visible = true
        launcher.raise()
        launcher.requestActivate()
        focusTimer.start()
    }

    function close() {
        launcher.visible = false
        searchBox.clear()
        filteredApps = []
        selectedIndex = 0
    }

    function launchSelected() {
        if (selectedIndex >= 0 && selectedIndex < filteredApps.length) {
            AppService.launch(filteredApps[selectedIndex])
            close()
        }
    }

    // Re-grab focus after the window is mapped — X11 may need a
    // short delay before XSetInputFocus succeeds.
    Timer {
        id: focusTimer
        interval: 50
        repeat: false
        onTriggered: {
            launcher.requestActivate()
            searchBox.forceActiveFocus()
            WindowHelper.grabKeyboard(launcher)
        }
    }

    Connections {
        target: IPCService
        function onOpenLauncherRequested() {
            if (launcher.visible)
                launcher.close()
            else
                launcher.open()
        }
    }

    // Dismiss on click outside the card
    MouseArea {
        anchors.fill: parent
        onClicked: launcher.close()
    }

    // ── Centered card ──────────────────────────────────────────────
    Rectangle {
        id: card
        width: 600
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.15
        height: Math.min(searchBarItem.height + separator.height + resultList.height + 15,
                         parent.height * 0.7)
        color: Theme.barBg
        radius: 16
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        // Card absorbs clicks so they don't close the launcher
        MouseArea { anchors.fill: parent }

        // ── Search bar ─────────────────────────────────────────────
        Item {
            id: searchBarItem
            width: parent.width
            height: 56

            LauncherSearchBox {
                id: searchBox
                anchors.fill: parent
                placeholderText: "Search applications\u2026"
                onQueryChanged: (text) => {
                    launcher.filteredApps = AppService.search(text)
                    launcher.selectedIndex = 0
                }
                onAccepted: launcher.launchSelected()
                onNextItem: {
                    launcher.selectedIndex = Math.min(
                        launcher.selectedIndex + 1,
                        launcher.filteredApps.length - 1)
                    resultList.positionViewAtIndex(launcher.selectedIndex, ListView.Contain)
                }
                onPrevItem: {
                    launcher.selectedIndex = Math.max(launcher.selectedIndex - 1, 0)
                    resultList.positionViewAtIndex(launcher.selectedIndex, ListView.Contain)
                }
                onDismissed: launcher.close()
            }
        }

        // ── Separator ──────────────────────────────────────────────
        Rectangle {
            id: separator
            anchors.top: searchBarItem.bottom
            width: parent.width
            height: 1
            color: Theme.menuBorder
            visible: resultList.count > 0 || (searchBox.text.length > 0 && noResultsText.visible)
        }

        // ── App list ───────────────────────────────────────────────
        ListView {
            id: resultList
            anchors.top: separator.bottom
            width: parent.width
            height: Math.min(contentHeight,
                             launcher.height * 0.7 - searchBarItem.height - separator.height)
            clip: true
            model: launcher.filteredApps
            currentIndex: launcher.selectedIndex
            highlightMoveDuration: 80
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true
            visible: count > 0

            delegate: Rectangle {
                id: delegateRoot
                required property var modelData
                required property int index
                width: resultList.width
                height: 56
                color: index === launcher.selectedIndex
                    ? Theme.menuHover
                    : delegateArea.containsMouse
                        ? Qt.rgba(Theme.menuHover.r, Theme.menuHover.g,
                                  Theme.menuHover.b, 0.5)
                        : "transparent"

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 20
                    spacing: 14

                    Item {
                        width: 36; height: 36
                        anchors.verticalCenter: parent.verticalCenter

                        Image {
                            id: appIcon
                            anchors.fill: parent
                            source: (delegateRoot.modelData.iconPath
                                     && delegateRoot.modelData.iconPath !== "")
                                ? delegateRoot.modelData.iconPath : ""
                            sourceSize: Qt.size(36, 36)
                            asynchronous: true
                            mipmap: true
                            visible: status === Image.Ready
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: appIcon.status !== Image.Ready
                            text: "\uf2d2"
                            font.family: Theme.iconFont
                            font.pixelSize: 22
                            color: Theme.dotOccupied
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        width: parent.width - 70

                        Text {
                            text: delegateRoot.modelData.name ?? ""
                            color: Theme.textColor
                            font.family: Theme.monoFont
                            font.pixelSize: 14
                            elide: Text.ElideRight
                            width: parent.width
                        }

                        Text {
                            text: delegateRoot.modelData.comment
                                  || delegateRoot.modelData.genericName || ""
                            color: Qt.alpha(Theme.textColor, 0.5)
                            font.family: Theme.monoFont
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            width: parent.width
                            visible: text.length > 0
                        }
                    }
                }

                MouseArea {
                    id: delegateArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        AppService.launch(delegateRoot.modelData)
                        launcher.close()
                    }
                    onEntered: launcher.selectedIndex = delegateRoot.index
                }
            }
        }

        Text {
            id: noResultsText
            anchors.top: separator.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 20
            visible: resultList.count === 0 && searchBox.text.length > 0
            text: "No applications found"
            color: Theme.dotOccupied
            font.family: Theme.monoFont
            font.pixelSize: 14
        }
    }
}
