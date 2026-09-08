import QtQuick
import QtQuick.Controls
import PyShell.Services 1.0
import "../shared"

Rectangle {
    id: systrayWidget

    property Item popupLayer: null
    property real menuX: 0
    property real menuY: Theme.barHeight + 4
    property var expandedMenus: ({})

    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg
    visible: SystrayService.items.length > 0
    width: systrayRow.width + Theme.containerPadding

    function requestInputUpdate() {
        if (popupLayer)
            Qt.callLater(popupLayer.updateInputRegion)
    }

    function closeTrayMenu() {
        SystrayService.closeMenu()
        expandedMenus = ({})
        if (popupLayer)
            popupLayer.systrayMenuVisible = false
    }

    function openTrayMenu(item, x, y) {
        menuX = Math.max(Theme.edgeMargin, x - Theme.menuWidth + Theme.containerHeight)
        menuY = Theme.barHeight + 4
        expandedMenus = ({})
        if (popupLayer)
            popupLayer.systrayMenuVisible = true
        SystrayService.openMenu(item.id, x, y)
        requestInputUpdate()
    }

    function toggleExpanded(id) {
        var next = {}
        for (var key in expandedMenus)
            next[key] = expandedMenus[key]
        next[id] = !next[id]
        expandedMenus = next
        requestInputUpdate()
    }

    function parentVisible(parentId) {
        if (parentId < 0)
            return true
        if (!expandedMenus[parentId])
            return false
        for (var i = 0; i < SystrayService.menuItems.length; i++) {
            var row = SystrayService.menuItems[i]
            if (row.id === parentId)
                return parentVisible(row.parentId)
        }
        return false
    }

    onVisibleChanged: requestInputUpdate()

    Connections {
        target: SystrayService
        function onMenuOpenForChanged() {
            if (SystrayService.menuOpenFor === "" && systrayWidget.popupLayer)
                systrayWidget.popupLayer.systrayMenuVisible = false
            systrayWidget.requestInputUpdate()
        }
        function onMenuItemsChanged() {
            systrayWidget.requestInputUpdate()
        }
    }

    Connections {
        target: FullscreenService
        function onHasFullscreenChanged() {
            SystrayService.setXEmbedVisible(!FullscreenService.hasFullscreen)
        }
    }

    Row {
        id: systrayRow
        anchors.centerIn: parent
        spacing: 4

        Repeater {
            model: SystrayService.items

            delegate: Rectangle {
                id: iconBtn
                required property var modelData
                required property int index

                width: Theme.containerHeight
                height: Theme.containerHeight
                radius: Theme.containerRadius
                color: iconArea.containsMouse ? Theme.menuHover : "transparent"
                opacity: iconBtn.modelData && iconBtn.modelData.passive ? 0.52 : 1.0

                function syncXEmbedGeometry() {
                    if (!iconBtn.modelData || iconBtn.modelData.source !== "xembed")
                        return
                    if (!iconBtn.visible || FullscreenService.hasFullscreen) {
                        SystrayService.setXEmbedGeometry(iconBtn.modelData.id, 0, 0, 0, 0)
                        return
                    }
                    var pos = iconBtn.mapToGlobal(0, 0)
                    SystrayService.setXEmbedGeometry(
                        iconBtn.modelData.id,
                        Math.round(pos.x),
                        Math.round(pos.y),
                        Math.round(iconBtn.width),
                        Math.round(iconBtn.height)
                    )
                }

                Component.onCompleted: Qt.callLater(syncXEmbedGeometry)
                Component.onDestruction: {
                    if (iconBtn.modelData && iconBtn.modelData.source === "xembed")
                        SystrayService.setXEmbedGeometry(iconBtn.modelData.id, 0, 0, 0, 0)
                }
                onXChanged: Qt.callLater(syncXEmbedGeometry)
                onYChanged: Qt.callLater(syncXEmbedGeometry)
                onWidthChanged: Qt.callLater(syncXEmbedGeometry)
                onHeightChanged: Qt.callLater(syncXEmbedGeometry)
                onVisibleChanged: Qt.callLater(syncXEmbedGeometry)

                Rectangle {
                    visible: iconBtn.modelData && iconBtn.modelData.attention
                    anchors.fill: parent
                    anchors.margins: 3
                    radius: Theme.containerRadius - 3
                    color: "transparent"
                    border.color: Theme.dotUrgent
                    border.width: 1
                }

                Image {
                    id: iconImage
                    anchors.centerIn: parent
                    width: Theme.iconFontSize
                    height: Theme.iconFontSize
                    sourceSize.width: Theme.iconFontSize * 2
                    sourceSize.height: Theme.iconFontSize * 2
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    antialiasing: true
                    visible: source !== ""
                    source: {
                        var item = iconBtn.modelData
                        if (!item || item.source === "xembed" || !item.iconBase64)
                            return ""
                        return "data:image/png;base64," + item.iconBase64
                    }
                }

                Text {
                    anchors.centerIn: parent
                    visible: iconBtn.modelData && iconBtn.modelData.source !== "xembed"
                             && (!iconImage.visible || iconImage.status !== Image.Ready)
                    text: "\uf2d0"
                    font.family: Theme.iconFont
                    font.pixelSize: Theme.iconFontSize
                    color: iconBtn.modelData && iconBtn.modelData.attention ? Theme.dotUrgent : Theme.textColor
                }

                ToolTip {
                    id: tooltip
                    visible: iconArea.containsMouse && iconBtn.modelData
                             && (iconBtn.modelData.tooltipTitle !== "" || iconBtn.modelData.title !== "")
                    delay: 600
                    text: {
                        var item = iconBtn.modelData
                        if (!item)
                            return ""
                        if (item.tooltipTitle && item.tooltipText)
                            return item.tooltipTitle + "\n" + item.tooltipText
                        return item.tooltipTitle || item.title || ""
                    }

                    background: Rectangle {
                        color: Theme.menuBg
                        radius: 6
                        border.color: Theme.menuBorder
                        border.width: 1
                    }
                    contentItem: Text {
                        text: tooltip.text
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize - 1
                    }
                }

                MouseArea {
                    id: iconArea
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !iconBtn.modelData || iconBtn.modelData.source !== "xembed"
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

                    onClicked: mouse => {
                        if (!iconBtn.modelData)
                            return
                        var item = iconBtn.modelData
                        var pos = iconBtn.mapToGlobal(iconBtn.width / 2, iconBtn.height / 2)
                        if (mouse.button === Qt.RightButton)
                            systrayWidget.openTrayMenu(item, pos.x, pos.y)
                        else if (mouse.button === Qt.MiddleButton)
                            SystrayService.secondaryActivate(item.id, pos.x, pos.y)
                        else
                            SystrayService.activate(item.id, pos.x, pos.y)
                    }

                    onWheel: wheel => {
                        if (!iconBtn.modelData)
                            return
                        var delta = wheel.angleDelta.y !== 0 ? wheel.angleDelta.y : wheel.angleDelta.x
                        var orientation = wheel.angleDelta.y !== 0 ? "vertical" : "horizontal"
                        SystrayService.scroll(iconBtn.modelData.id, delta, orientation)
                    }
                }
            }
        }
    }

    Rectangle {
        id: trayMenu
        parent: systrayWidget.popupLayer
        visible: SystrayService.menuOpenFor !== "" && SystrayService.menuItems.length > 0
        x: systrayWidget.menuX
        y: systrayWidget.menuY
        width: Theme.menuWidth
        height: Math.min(menuColumn.implicitHeight + 12, 420)
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1
        clip: true

        onVisibleChanged: systrayWidget.requestInputUpdate()
        onHeightChanged: systrayWidget.requestInputUpdate()

        Column {
            id: menuColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            topPadding: 6
            bottomPadding: 6

            Repeater {
                model: SystrayService.menuItems

                delegate: Item {
                    id: menuRow
                    required property var modelData

                    width: menuColumn.width
                    height: visible ? (modelData.type === "separator" ? 9 : (modelData.imagePreview ? 74 : Theme.menuItemHeight)) : 0
                    visible: systrayWidget.parentVisible(modelData.parentId)

                    Rectangle {
                        visible: modelData.type === "separator"
                        x: 14 + (modelData.depth * 12)
                        y: 4
                        width: parent.width - x - 14
                        height: 1
                        color: Qt.alpha(Theme.menuBorder, 0.85)
                    }

                    Rectangle {
                        id: itemBg
                        visible: modelData.type !== "separator"
                        x: 5 + (modelData.depth * 12)
                        y: 2
                        width: parent.width - x - 5
                        height: menuRow.height - 4
                        radius: Theme.containerRadius - 2
                        color: menuArea.containsMouse && modelData.enabled ? Theme.menuHover : "transparent"

                        Text {
                            id: checkMark
                            width: 18
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.toggleType === "" ? "" : (modelData.toggleState > 0 ? "\uf00c" : "")
                            font.family: Theme.iconFont
                            font.pixelSize: 12
                            color: Qt.alpha(Theme.textColor, 0.7)
                        }

                        Image {
                            id: menuIcon
                            anchors.left: checkMark.right
                            anchors.leftMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: modelData.imagePreview ? 72 : 16
                            height: modelData.imagePreview ? 56 : 16
                            fillMode: Image.PreserveAspectFit
                            visible: modelData.iconBase64 !== ""
                            source: visible ? "data:image/png;base64," + modelData.iconBase64 : ""
                        }

                        Text {
                            anchors.left: menuIcon.visible ? menuIcon.right : checkMark.right
                            anchors.leftMargin: 8
                            anchors.right: chevron.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.label
                            elide: Text.ElideRight
                            color: modelData.enabled ? Theme.textColor : Qt.alpha(Theme.textColor, 0.38)
                            font.family: Theme.monoFont
                            font.pixelSize: Theme.textFontSize
                        }

                        Text {
                            id: chevron
                            anchors.right: parent.right
                            anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.hasChildren ? (systrayWidget.expandedMenus[modelData.id] ? "\uf078" : "\uf054") : ""
                            font.family: Theme.iconFont
                            font.pixelSize: 10
                            color: Qt.alpha(Theme.textColor, 0.5)
                        }
                    }

                    MouseArea {
                        id: menuArea
                        x: itemBg.x
                        y: itemBg.y
                        width: itemBg.width
                        height: itemBg.height
                        visible: modelData.type !== "separator"
                        hoverEnabled: true
                        cursorShape: modelData.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (!modelData.enabled)
                                return
                            if (modelData.hasChildren) {
                                systrayWidget.toggleExpanded(modelData.id)
                                return
                            }
                            SystrayService.triggerMenuItem(SystrayService.menuOpenFor, modelData.id)
                            if (systrayWidget.popupLayer)
                                systrayWidget.popupLayer.systrayMenuVisible = false
                        }
                    }
                }
            }
        }
    }
}
