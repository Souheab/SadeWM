import QtQuick
import QtQuick.Window
import "../shared"
import PyShell.Services 1.0

Window {
    id: picker

    visible: false
    color: "#80000000"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint

    x: 0
    y: 0
    width: Screen.width
    height: Screen.height

    property var filteredEmoji: []
    property int selectedIndex: 0

    function open() {
        filteredEmoji = EmojiService.search("")
        selectedIndex = 0
        searchBox.clear()
        picker.visible = true
        picker.raise()
        picker.requestActivate()
        focusTimer.start()
    }

    function close() {
        picker.visible = false
        searchBox.clear()
        filteredEmoji = []
        selectedIndex = 0
    }

    function pickSelected() {
        if (selectedIndex >= 0 && selectedIndex < filteredEmoji.length) {
            var emoji = filteredEmoji[selectedIndex]
            EmojiService.copyToClipboard(emoji.char)
            close()
        }
    }

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

    Connections {
        target: IPCService
        function onOpenEmojiPickerRequested() {
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

        // Card absorbs clicks so they don't close the picker
        MouseArea { anchors.fill: parent }

        // ── Search bar ─────────────────────────────────────────────
        Item {
            id: searchBarItem
            width: parent.width
            height: 56

            LauncherSearchBox {
                id: searchBox
                anchors.fill: parent
                placeholderText: "Search emoji\u2026"
                iconGlyph: "\uf118"   // fa-smile
                onQueryChanged: (text) => {
                    picker.filteredEmoji = EmojiService.search(text)
                    picker.selectedIndex = 0
                }
                onAccepted: picker.pickSelected()
                onNextItem: {
                    picker.selectedIndex = Math.min(
                        picker.selectedIndex + 1, picker.filteredEmoji.length - 1)
                    resultList.positionViewAtIndex(picker.selectedIndex, ListView.Contain)
                }
                onPrevItem: {
                    picker.selectedIndex = Math.max(picker.selectedIndex - 1, 0)
                    resultList.positionViewAtIndex(picker.selectedIndex, ListView.Contain)
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
            visible: resultList.count > 0 || (searchBox.text.length > 0 && noResultsText.visible)
        }

        // ── Emoji list ─────────────────────────────────────────────
        ListView {
            id: resultList
            anchors.top: separator.bottom
            width: parent.width
            height: Math.min(contentHeight,
                             picker.height * 0.7 - searchBarItem.height - separator.height)
            clip: true
            model: picker.filteredEmoji
            currentIndex: picker.selectedIndex
            highlightMoveDuration: 80
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true
            visible: count > 0

            delegate: Rectangle {
                id: delegateRoot
                required property var modelData
                required property int index
                width: resultList.width
                height: 52
                color: index === picker.selectedIndex
                    ? Theme.menuHover
                    : delegateArea.containsMouse
                        ? Qt.rgba(Theme.menuHover.r, Theme.menuHover.g,
                                  Theme.menuHover.b, 0.5)
                        : "transparent"

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 20
                    spacing: 16

                    // Emoji character display
                    Text {
                        text: delegateRoot.modelData.char ?? ""
                        font.pixelSize: 26
                        anchors.verticalCenter: parent.verticalCenter
                        width: 36
                        horizontalAlignment: Text.AlignHCenter
                    }

                    // Emoji name
                    Text {
                        text: delegateRoot.modelData.name ?? ""
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: 14
                        elide: Text.ElideRight
                        width: parent.width - 36 - 16
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                MouseArea {
                    id: delegateArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        EmojiService.copyToClipboard(delegateRoot.modelData.char)
                        picker.close()
                    }
                    onEntered: picker.selectedIndex = delegateRoot.index
                }
            }
        }

        Text {
            id: noResultsText
            anchors.top: separator.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 20
            visible: resultList.count === 0 && searchBox.text.length > 0
            text: "No emoji found"
            color: Theme.dotOccupied
            font.family: Theme.monoFont
            font.pixelSize: 14
        }
    }
}
