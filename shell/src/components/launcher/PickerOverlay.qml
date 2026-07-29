pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import "../shared"
import PyShell.Services 1.0

Window {
    id: picker

    property bool minimizedOnly: false
    property int selectedIndex: 0
    property string searchQuery: ""
    property bool opened: false
    property bool awaitingInitialResults: false

    readonly property var windowModel: minimizedOnly
        ? WindowPickerService.minimizedWindowsModel
        : WindowPickerService.windowsModel
    readonly property bool refreshing: minimizedOnly
        ? WindowPickerService.minimizedRefreshing
        : WindowPickerService.refreshing
    readonly property int windowCount: windowModel.count
    readonly property int gridPadding: 12
    readonly property int cardSpacing: 14
    readonly property int windowCardWidth: minimizedOnly ? 310 : 236
    readonly property int windowCardHeight: minimizedOnly ? 92 : 190
    readonly property int cellWidth: windowCardWidth + cardSpacing
    readonly property int cellHeight: windowCardHeight + cardSpacing
    readonly property int maxColumns: minimizedOnly ? 3 : 5
    readonly property int availableColumns: Math.max(
        1,
        Math.floor((width * 0.92 - gridPadding * 2) / cellWidth)
    )
    readonly property int columns: Math.max(
        1,
        Math.min(maxColumns, Math.max(1, windowCount), availableColumns)
    )
    readonly property int rows: windowCount > 0
        ? Math.ceil(windowCount / columns)
        : 0
    readonly property int desiredGridHeight: windowCount > 0
        ? rows * cellHeight + gridPadding * 2
        : 104

    visible: false
    opacity: 0
    color: "#99000000"
    flags: Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.X11BypassWindowManagerHint

    x: Screen.virtualX
    y: Screen.virtualY
    width: Screen.width
    height: Screen.height

    function placeOnActiveScreen() {
        var activeScreen = WindowHelper.activeScreen()
        if (activeScreen)
            picker.screen = activeScreen
    }

    function open() {
        if (opened)
            return

        closingAnimation.stop()
        placeOnActiveScreen()
        opened = true
        visible = true
        opacity = 0
        card.scale = 0.97
        selectedIndex = 0
        searchQuery = ""
        awaitingInitialResults = true
        searchBox.clear()
        windowModel.setFilter("")

        if (minimizedOnly)
            WindowPickerService.refreshMinimized()
        else
            WindowPickerService.refresh()

        raise()
        requestActivate()
        openingAnimation.restart()
        focusTimer.start()
    }

    function close() {
        if (!opened)
            return
        opened = false
        focusTimer.stop()
        openingAnimation.stop()
        closingAnimation.restart()
        searchQuery = ""
        selectedIndex = 0
    }

    function finishClose() {
        if (!opened)
            visible = false
    }

    function applyFilter(query) {
        searchQuery = query
        windowModel.setFilter(query)
        selectedIndex = windowCount > 0 ? 0 : -1
        positionSelection()
    }

    function setInitialSelection() {
        if (windowCount <= 0) {
            selectedIndex = -1
            return
        }

        selectedIndex = 0
        positionSelection()
    }

    function handleModelChanged() {
        if (!opened)
            return
        if (awaitingInitialResults) {
            awaitingInitialResults = false
            setInitialSelection()
        } else if (selectedIndex >= windowCount) {
            selectedIndex = Math.max(0, windowCount - 1)
        }
    }

    function positionSelection() {
        if (selectedIndex >= 0)
            gridView.positionViewAtIndex(selectedIndex, GridView.Contain)
    }

    function moveLinear(delta) {
        if (windowCount <= 0)
            return
        selectedIndex = (selectedIndex + delta + windowCount) % windowCount
        positionSelection()
    }

    function moveHorizontal(delta) {
        if (windowCount <= 0)
            return
        selectedIndex = Math.max(
            0,
            Math.min(windowCount - 1, selectedIndex + delta)
        )
        positionSelection()
    }

    function moveVertical(delta) {
        if (windowCount <= 0)
            return
        selectedIndex = Math.max(
            0,
            Math.min(windowCount - 1, selectedIndex + delta * columns)
        )
        positionSelection()
    }

    function selectWindow() {
        if (selectedIndex >= 0 && selectedIndex < windowCount) {
            var entry = windowModel.get(selectedIndex)
            WindowPickerService.focusWindow(entry.winId)
            close()
        }
    }

    Timer {
        id: focusTimer
        interval: 40
        repeat: false
        onTriggered: {
            if (!picker.opened)
                return
            picker.requestActivate()
            searchBox.forceActiveFocus()
            WindowHelper.focusKeyboard(picker)
        }
    }

    ParallelAnimation {
        id: openingAnimation
        NumberAnimation {
            target: picker
            property: "opacity"
            from: 0
            to: 1
            duration: 120
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: card
            property: "scale"
            from: 0.97
            to: 1
            duration: 140
            easing.type: Easing.OutCubic
        }
    }

    ParallelAnimation {
        id: closingAnimation
        NumberAnimation {
            target: picker
            property: "opacity"
            to: 0
            duration: 90
            easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: card
            property: "scale"
            to: 0.98
            duration: 90
            easing.type: Easing.InCubic
        }
        onFinished: picker.finishClose()
    }

    Connections {
        target: WindowPickerService

        function onWindowsChanged() {
            if (!picker.minimizedOnly)
                picker.handleModelChanged()
        }

        function onMinimizedWindowsChanged() {
            if (picker.minimizedOnly)
                picker.handleModelChanged()
        }

        function onRefreshingChanged() {
            if (!picker.minimizedOnly
                    && !WindowPickerService.refreshing
                    && picker.awaitingInitialResults) {
                picker.awaitingInitialResults = false
                picker.setInitialSelection()
            }
        }

        function onMinimizedRefreshingChanged() {
            if (picker.minimizedOnly
                    && !WindowPickerService.minimizedRefreshing
                    && picker.awaitingInitialResults) {
                picker.awaitingInitialResults = false
                picker.setInitialSelection()
            }
        }
    }

    Connections {
        target: IPCService

        function onOpenWindowPickerRequested() {
            if (picker.minimizedOnly)
                return
            if (picker.opened)
                picker.close()
            else
                picker.open()
        }

        function onOpenMinimizedPickerRequested() {
            if (!picker.minimizedOnly)
                return
            if (picker.opened)
                picker.close()
            else
                picker.open()
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: picker.close()
    }

    Rectangle {
        id: card
        width: Math.min(
            picker.columns * picker.cellWidth + picker.gridPadding * 2,
            parent.width * 0.92
        )
        height: searchBarItem.height
            + separator.height
            + gridArea.height
            + footer.height
        anchors.centerIn: parent
        color: Theme.barBg
        radius: 16
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        MouseArea {
            anchors.fill: parent
        }

        Item {
            id: searchBarItem
            width: parent.width
            height: 60

            LauncherSearchBox {
                id: searchBox
                anchors.fill: parent
                placeholderText: picker.minimizedOnly
                    ? "Restore minimized window\u2026"
                    : "Search open windows\u2026"
                iconGlyph: picker.minimizedOnly ? "\uf2d1" : "\uf002"
                hintText: picker.refreshing
                    ? "Refreshing\u2026"
                    : "\u2191\u2193\u2190\u2192 navigate  \u00b7  Enter select"

                onQueryChanged: (text) => picker.applyFilter(text)
                onAccepted: picker.selectWindow()
                onNextItem: picker.moveVertical(1)
                onPrevItem: picker.moveVertical(-1)
                onNextColumn: picker.moveHorizontal(1)
                onPrevColumn: picker.moveHorizontal(-1)
                onNextLinear: picker.moveLinear(1)
                onPrevLinear: picker.moveLinear(-1)
                onDismissed: picker.close()
            }
        }

        Rectangle {
            id: separator
            anchors.top: searchBarItem.bottom
            width: parent.width
            height: 1
            color: Theme.menuBorder
        }

        Item {
            id: gridArea
            anchors.top: separator.bottom
            width: parent.width
            height: Math.min(
                picker.desiredGridHeight,
                picker.height * 0.76
                    - searchBarItem.height
                    - separator.height
                    - footer.height
            )
            clip: true

            Column {
                anchors.centerIn: parent
                width: parent.width - 32
                spacing: 8
                visible: gridView.count === 0

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: picker.refreshing ? "\uf110" : "\uf2d2"
                    color: picker.refreshing
                        ? Theme.dotSelected
                        : Theme.dotEmpty
                    font.family: Theme.iconFont
                    font.pixelSize: 24

                    RotationAnimator on rotation {
                        running: picker.refreshing
                        from: 0
                        to: 360
                        duration: 900
                        loops: Animation.Infinite
                    }
                }

                Text {
                    width: parent.width
                    text: {
                        if (picker.refreshing)
                            return picker.minimizedOnly
                                ? "Loading minimized windows\u2026"
                                : "Loading windows\u2026"
                        if (picker.searchQuery.length > 0)
                            return "No windows match \u201c"
                                + picker.searchQuery + "\u201d"
                        return picker.minimizedOnly
                            ? "No minimized windows on this workspace"
                            : "No open windows"
                    }
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
            }

            GridView {
                id: gridView
                anchors {
                    fill: parent
                    margins: picker.gridPadding
                }
                cellWidth: picker.cellWidth
                cellHeight: picker.cellHeight
                model: picker.windowModel
                currentIndex: picker.selectedIndex
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Item {
                    id: delegateRoot

                    required property int index
                    required property int winId
                    required property string name
                    required property string wmClass
                    required property int tagNum
                    required property string workspaceLabel
                    required property bool focused
                    required property bool minimized
                    required property string iconUri
                    required property string thumbnailUri

                    width: gridView.cellWidth
                    height: gridView.cellHeight

                    Rectangle {
                        id: winCard
                        width: picker.windowCardWidth
                        height: picker.windowCardHeight
                        anchors.centerIn: parent
                        radius: 10
                        color: delegateRoot.index === picker.selectedIndex
                            ? Qt.rgba(
                                Theme.dotSelected.r,
                                Theme.dotSelected.g,
                                Theme.dotSelected.b,
                                0.18
                            )
                            : cardArea.containsMouse
                                ? Theme.menuHover
                                : Theme.containerBg
                        border.color: delegateRoot.index === picker.selectedIndex
                            ? Theme.dotSelected
                            : Theme.menuBorder
                        border.width: delegateRoot.index === picker.selectedIndex
                            ? 2
                            : 1
                        clip: true

                        Behavior on color {
                            ColorAnimation { duration: 80 }
                        }

                        Behavior on border.color {
                            ColorAnimation { duration: 80 }
                        }

                        MouseArea {
                            id: cardArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: picker.selectedIndex = delegateRoot.index
                            onClicked: {
                                picker.selectedIndex = delegateRoot.index
                                picker.selectWindow()
                            }
                        }

                        Rectangle {
                            id: thumbArea
                            visible: !picker.minimizedOnly
                            anchors {
                                top: parent.top
                                left: parent.left
                                right: parent.right
                                bottom: normalLabels.top
                            }
                            color: "#14151f"
                            radius: 10
                            clip: true

                            Image {
                                id: thumbImg
                                anchors.fill: parent
                                anchors.margins: 4
                                source: delegateRoot.thumbnailUri || ""
                                sourceSize: Qt.size(228, 134)
                                fillMode: Image.PreserveAspectFit
                                asynchronous: false
                                mipmap: false
                                visible: status === Image.Ready
                                smooth: true
                            }

                            Text {
                                anchors.centerIn: parent
                                visible: thumbImg.status !== Image.Ready
                                text: "\uf2d2"
                                font.family: Theme.iconFont
                                font.pixelSize: 36
                                color: Theme.dotEmpty
                            }

                            Rectangle {
                                anchors {
                                    top: parent.top
                                    right: parent.right
                                    margins: 7
                                }
                                width: workspaceText.implicitWidth + 12
                                height: 20
                                radius: 5
                                color: "#e61a1b26"
                                visible: delegateRoot.workspaceLabel.length > 0

                                Text {
                                    id: workspaceText
                                    anchors.centerIn: parent
                                    text: "Workspace " + delegateRoot.workspaceLabel
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 9
                                }
                            }

                            Rectangle {
                                anchors {
                                    bottom: parent.bottom
                                    left: parent.left
                                    margins: 7
                                }
                                width: 32
                                height: 32
                                radius: 7
                                color: "#e61a1b26"

                                Image {
                                    id: winIconImg
                                    anchors {
                                        fill: parent
                                        margins: 4
                                    }
                                    source: delegateRoot.iconUri || ""
                                    sourceSize: Qt.size(24, 24)
                                    asynchronous: false
                                    mipmap: false
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

                        Item {
                            id: normalLabels
                            visible: !picker.minimizedOnly
                            anchors {
                                bottom: parent.bottom
                                left: parent.left
                                right: parent.right
                            }
                            height: 50

                            Column {
                                anchors {
                                    left: parent.left
                                    right: parent.right
                                    verticalCenter: parent.verticalCenter
                                    leftMargin: 10
                                    rightMargin: 10
                                }
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: delegateRoot.name
                                        || delegateRoot.wmClass
                                        || "Unknown window"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: {
                                        var app = delegateRoot.wmClass || "Application"
                                        return delegateRoot.focused
                                            ? app + "  \u00b7  Current"
                                            : app
                                    }
                                    color: Qt.alpha(Theme.textColor, 0.62)
                                    font.family: Theme.monoFont
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Row {
                            id: minimizedContent
                            visible: picker.minimizedOnly
                            anchors {
                                fill: parent
                                margins: 14
                            }
                            spacing: 12

                            Item {
                                width: 46
                                height: 46
                                anchors.verticalCenter: parent.verticalCenter

                                Image {
                                    id: minimizedIcon
                                    anchors.fill: parent
                                    source: delegateRoot.iconUri || ""
                                    sourceSize: Qt.size(46, 46)
                                    asynchronous: false
                                    mipmap: false
                                    visible: status === Image.Ready
                                    smooth: true
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    visible: minimizedIcon.status !== Image.Ready
                                    radius: 9
                                    color: Theme.barBg

                                    Text {
                                        anchors.centerIn: parent
                                        text: "\uf2d1"
                                        font.family: Theme.iconFont
                                        font.pixelSize: 22
                                        color: Theme.dotOccupied
                                    }
                                }
                            }

                            Column {
                                width: parent.width - 46 - minimizedBadge.width - 32
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 5

                                Text {
                                    width: parent.width
                                    text: delegateRoot.name
                                        || delegateRoot.wmClass
                                        || "Unknown window"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: {
                                        var metadata = delegateRoot.wmClass || "Application"
                                        if (delegateRoot.workspaceLabel.length > 0)
                                            metadata += "  \u00b7  Workspace "
                                                + delegateRoot.workspaceLabel
                                        return metadata
                                    }
                                    color: Qt.alpha(Theme.textColor, 0.62)
                                    font.family: Theme.monoFont
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }

                            Rectangle {
                                id: minimizedBadge
                                width: 70
                                height: 22
                                anchors.verticalCenter: parent.verticalCenter
                                radius: 6
                                color: Qt.rgba(
                                    Theme.dotSelected.r,
                                    Theme.dotSelected.g,
                                    Theme.dotSelected.b,
                                    0.14
                                )
                                border.color: Qt.alpha(Theme.dotSelected, 0.45)

                                Text {
                                    anchors.centerIn: parent
                                    text: "Minimized"
                                    color: Theme.dotSelected
                                    font.family: Theme.monoFont
                                    font.pixelSize: 8
                                }
                            }
                        }
                    }
                }
            }
        }

        Item {
            id: footer
            anchors.top: gridArea.bottom
            width: parent.width
            height: 34

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: Theme.menuBorder
            }

            Text {
                anchors {
                    left: parent.left
                    leftMargin: 14
                    verticalCenter: parent.verticalCenter
                }
                text: picker.refreshing
                    ? "Refreshing\u2026"
                    : picker.windowCount + (picker.windowCount === 1
                        ? " window"
                        : " windows")
                color: Qt.alpha(Theme.textColor, 0.52)
                font.family: Theme.monoFont
                font.pixelSize: 9
            }

            Text {
                anchors {
                    right: parent.right
                    rightMargin: 14
                    verticalCenter: parent.verticalCenter
                }
                text: "Type to search  \u00b7  Enter select  \u00b7  Esc close"
                color: Qt.alpha(Theme.textColor, 0.52)
                font.family: Theme.monoFont
                font.pixelSize: 9
                visible: parent.width >= 420
            }
        }
    }
}
