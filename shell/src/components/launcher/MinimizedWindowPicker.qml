import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "../shared"
import PyShell.Services 1.0

Window {
    id: picker

    visible: false
    color: "#cc000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    // All windows from service, filtered by search query
    property var allWindows: []
    property var filteredWindows: []
    property int selectedIndex: 0
    property string searchQuery: ""

    // Number of columns in the grid — always up to 5 per row
    readonly property int cols: Math.max(1, Math.min(5, filteredWindows.length))
    readonly property int cardW: 220
    readonly property int cardH: 180
    readonly property int cardSpacing: 14

    function open() {
        searchQuery = ""
        selectedIndex = 0
        searchBox.clear()
        WindowPickerService.refreshMinimized()
        picker.visible = true
        picker.raise()
        picker.requestActivate()
        focusTimer.start()
    }

    function close() {
        picker.visible = false
        searchQuery = ""
        selectedIndex = 0
    }

    function _applyFilter(query) {
        var q = query.toLowerCase().trim()
        var result = []
        for (var i = 0; i < allWindows.length; i++) {
            var w = allWindows[i]
            if (q === "" ||
                w.name.toLowerCase().indexOf(q) !== -1 ||
                w.wmClass.toLowerCase().indexOf(q) !== -1) {
                result.push(w)
            }
        }
        filteredWindows = result
        if (selectedIndex >= filteredWindows.length) {
            selectedIndex = Math.max(0, filteredWindows.length - 1)
        }
    }

    function selectWindow() {
        if (selectedIndex >= 0 && selectedIndex < filteredWindows.length) {
            var w = filteredWindows[selectedIndex]
            WindowPickerService.focusWindow(w.winId)
            close()
        }
    }

    // Re-grab focus after mapping
    Timer {
        id: focusTimer
        interval: 50
        repeat: false
        onTriggered: {
            picker.requestActivate()
            searchBox.forceActiveFocus()
            WindowHelper.grabKeyboard(picker)
        }
    }

    // React to service updates
    Connections {
        target: WindowPickerService
        function onWindowsChanged() {
            picker.allWindows = WindowPickerService.windows
            picker._applyFilter(picker.searchQuery)
        }
    }

    // React to IPC open request
    Connections {
        target: IPCService
        function onOpenMinimizedPickerRequested() {
            if (picker.visible)
                picker.close()
            else
                picker.open()
        }
    }

    // Dismiss on click outside the card
    MouseArea {
        anchors.fill: parent
        onClicked: picker.close()
    }

    // Left/Right arrow navigation for grid columns
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Right) {
            picker.selectedIndex = Math.min(
                picker.selectedIndex + 1,
                picker.filteredWindows.length - 1)
            gridView.positionViewAtIndex(picker.selectedIndex, GridView.Contain)
            event.accepted = true
        } else if (event.key === Qt.Key_Left) {
            picker.selectedIndex = Math.max(picker.selectedIndex - 1, 0)
            gridView.positionViewAtIndex(picker.selectedIndex, GridView.Contain)
            event.accepted = true
        }
    }

    // ── Centered card ──────────────────────────────────────────────
    Rectangle {
        id: card
        width: Math.min(
            picker.cols * (picker.cardW + picker.cardSpacing) + picker.cardSpacing + 2,
            parent.width * 0.92
        )
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        height: Math.min(
            searchBarItem.height + separator.height + gridArea.height + 24,
            parent.height * 0.88
        )
        color: Theme.barBg
        radius: 16
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        MouseArea { anchors.fill: parent }

        // ── Search bar ─────────────────────────────────────────────
        Item {
            id: searchBarItem
            width: parent.width
            height: 56

            LauncherSearchBox {
                id: searchBox
                anchors.fill: parent
                placeholderText: "Restore minimized window\u2026"
                iconGlyph: "\uf2d1"   // window-minimize icon
                onQueryChanged: (text) => {
                    picker.searchQuery = text
                    picker._applyFilter(text)
                }
                onAccepted: picker.selectWindow()
                onNextItem: {
                    picker.selectedIndex = Math.min(
                        picker.selectedIndex + picker.cols,
                        picker.filteredWindows.length - 1)
                    gridView.positionViewAtIndex(picker.selectedIndex, GridView.Contain)
                }
                onPrevItem: {
                    picker.selectedIndex = Math.max(picker.selectedIndex - picker.cols, 0)
                    gridView.positionViewAtIndex(picker.selectedIndex, GridView.Contain)
                }
                onDismissed: picker.close()
            }
        }

        // ── Separator ──────────────────────────────────────────────
        Rectangle {
            id: separator
            anchors.top: searchBarItem.bottom
            width: parent.width
            height: 1
            color: Theme.menuBorder
            visible: gridView.count > 0 || noResultsText.visible
        }

        // ── Grid area ──────────────────────────────────────────────
        Item {
            id: gridArea
            anchors.top: separator.bottom
            width: parent.width
            height: Math.min(
                gridView.contentHeight + 16,
                picker.height * 0.75 - searchBarItem.height - separator.height
            )
            clip: true

            // No results
            Text {
                id: noResultsText
                anchors.centerIn: parent
                visible: gridView.count === 0
                text: "No minimized windows"
                color: Theme.dotOccupied
                font.family: Theme.monoFont
                font.pixelSize: 14
            }

            GridView {
                id: gridView
                anchors {
                    fill: parent
                    margins: 12
                }
                cellWidth: picker.cardW + picker.cardSpacing
                cellHeight: picker.cardH + picker.cardSpacing
                model: picker.filteredWindows
                currentIndex: picker.selectedIndex
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                delegate: Item {
                    id: delegateRoot
                    required property var modelData
                    required property int index
                    width: gridView.cellWidth
                    height: gridView.cellHeight

                    // ── Window card ────────────────────────────────
                    Rectangle {
                        id: winCard
                        width: picker.cardW
                        height: picker.cardH
                        anchors.centerIn: parent
                        radius: 10
                        color: delegateRoot.index === picker.selectedIndex
                            ? Qt.rgba(Theme.dotSelected.r, Theme.dotSelected.g,
                                      Theme.dotSelected.b, 0.18)
                            : cardHover.containsMouse
                                ? Theme.menuHover
                                : Theme.containerBg
                        border.color: delegateRoot.index === picker.selectedIndex
                            ? Theme.dotSelected
                            : Theme.menuBorder
                        border.width: delegateRoot.index === picker.selectedIndex ? 2 : 1
                        clip: true

                        MouseArea {
                            id: cardHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                picker.selectedIndex = delegateRoot.index
                                picker.selectWindow()
                            }
                        }

                        // ── Thumbnail area ─────────────────────────
                        Rectangle {
                            id: thumbArea
                            anchors {
                                top: parent.top
                                left: parent.left
                                right: parent.right
                                bottom: labelRow.top
                            }
                            color: "#14151f"
                            radius: 10
                            clip: true

                            // Placeholder (minimized windows have no thumbnail)
                            Text {
                                anchors.centerIn: parent
                                text: "\uf2d1"
                                font.family: Theme.iconFont
                                font.pixelSize: 36
                                color: Theme.dotEmpty
                            }

                            // Tag badge (top-right)
                            Rectangle {
                                anchors {
                                    top: parent.top
                                    right: parent.right
                                    margins: 6
                                }
                                width: tagLabel.implicitWidth + 10
                                height: 18
                                radius: 4
                                color: "#cc1a1b26"
                                visible: delegateRoot.modelData.tagNum > 0

                                Text {
                                    id: tagLabel
                                    anchors.centerIn: parent
                                    text: delegateRoot.modelData.tagNum > 0
                                        ? String(delegateRoot.modelData.tagNum) : ""
                                    color: Theme.dotOccupied
                                    font.family: Theme.monoFont
                                    font.pixelSize: 11
                                }
                            }

                            // ── Window icon (bottom-left of thumb) ─
                            Rectangle {
                                anchors {
                                    bottom: parent.bottom
                                    left: parent.left
                                    margins: 6
                                }
                                width: 30
                                height: 30
                                radius: 6
                                color: "#cc1a1b26"

                                Image {
                                    id: winIconImg
                                    anchors {
                                        fill: parent
                                        margins: 3
                                    }
                                    source: delegateRoot.modelData.iconUri || ""
                                    sourceSize: Qt.size(24, 24)
                                    asynchronous: true
                                    mipmap: true
                                    cache: false
                                    visible: status === Image.Ready
                                    smooth: true
                                }

                                Text {
                                    anchors.centerIn: parent
                                    visible: winIconImg.status !== Image.Ready
                                    text: "\uf2d2"
                                    font.family: Theme.iconFont
                                    font.pixelSize: 16
                                    color: Theme.dotOccupied
                                }
                            }
                        }

                        // ── App name label ─────────────────────────
                        Item {
                            id: labelRow
                            anchors {
                                bottom: parent.bottom
                                left: parent.left
                                right: parent.right
                            }
                            height: 36

                            Text {
                                anchors {
                                    verticalCenter: parent.verticalCenter
                                    left: parent.left
                                    right: parent.right
                                    leftMargin: 10
                                    rightMargin: 10
                                }
                                text: {
                                    var n = delegateRoot.modelData.wmClass ||
                                            delegateRoot.modelData.name || "Unknown"
                                    return n
                                }
                                color: delegateRoot.index === picker.selectedIndex
                                    ? Theme.textColor
                                    : Theme.dotOccupied
                                font.family: Theme.monoFont
                                font.pixelSize: 12
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }
                }
            }
        }
    }
}
