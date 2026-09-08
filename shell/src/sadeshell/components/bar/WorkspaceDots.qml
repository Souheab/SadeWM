import QtQuick
import PyShell.Services 1.0
import "../shared"

Row {
    id: workspaceDots
    spacing: 6

    readonly property Item popupLayer: {
        let p = parent;
        while (p) {
            for (let i = 0; i < p.children.length; i++) {
                if (p.children[i].objectName === "popupLayer")
                    return p.children[i];
            }
            p = p.parent;
        }
        return null;
    }

    property bool menuOpen: false
    property real popupX: 0
    property real popupY: 0

    function updatePopupPosition() {
        if (!popupLayer) return;
        const pos = logoBtn.mapToItem(popupLayer, 0, logoBtn.height);
        popupX = pos.x;
        popupY = pos.y + 4;
    }

    onMenuOpenChanged: {
        if (popupLayer) popupLayer.popupVisible = menuOpen;
    }

    Connections {
        target: workspaceDots.popupLayer
        function onPopupVisibleChanged() {
            if (workspaceDots.popupLayer && !workspaceDots.popupLayer.popupVisible)
                workspaceDots.menuOpen = false;
        }
    }

    // Logo button
    Rectangle {
        id: logoBtn
        width: Theme.containerHeight
        height: Theme.containerHeight
        radius: Theme.containerRadius
        color: logoArea.containsMouse ? Theme.menuHover : Theme.containerBg
        anchors.verticalCenter: parent.verticalCenter

        Image {
            source: Theme.logoSource
            width: Theme.logoSize
            height: Theme.logoSize
            anchors.centerIn: parent
            sourceSize.width: Theme.logoSize
            sourceSize.height: Theme.logoSize
        }

        MouseArea {
            id: logoArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (workspaceDots.menuOpen) {
                    workspaceDots.menuOpen = false;
                } else {
                    workspaceDots.updatePopupPosition();
                    workspaceDots.menuOpen = true;
                }
            }
        }
    }

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: tagRow.width + Theme.containerPadding
        height: Theme.containerHeight
        radius: Theme.containerRadius
        color: Theme.containerBg

        Row {
            id: tagRow
            anchors.centerIn: parent
            spacing: Theme.dotSpacing

            Repeater {
                model: Theme.tagCount

                Rectangle {
                    required property int index

                    width: (Theme.dotExpansion && isSelected) ? Theme.dotActiveWidth : Theme.dotSize
                    height: Theme.dotSize
                    radius: Theme.dotSize / 2
                    anchors.verticalCenter: parent.verticalCenter

                    Behavior on width {
                        enabled: Theme.dotExpansion
                        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                    }

                    property int tagNum: index + 1
                    property string tagState: (TagService.tags && TagService.tags.length > index) ? TagService.tags[index] : "I"
                    property bool isUrgent:   tagState === "U"
                    property bool isSelected: tagState === "A"
                    property bool isOccupied: tagState === "O"

                    color: {
                        if (isUrgent)   return dotArea.containsMouse ? Qt.darker(Theme.dotUrgent,   1.25) : Theme.dotUrgent
                        if (isSelected) return dotArea.containsMouse ? Qt.darker(Theme.dotSelected, 1.25) : Theme.dotSelected
                        if (isOccupied) return dotArea.containsMouse ? Qt.darker(Theme.dotOccupied, 1.25) : Theme.dotOccupied
                        return dotArea.containsMouse ? Qt.darker(Theme.dotEmpty, 1.4) : Theme.dotEmpty
                    }

                    MouseArea {
                        id: dotArea
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: Qt.PointingHandCursor

                        onClicked: mouse => {
                            if (mouse.button === Qt.LeftButton) {
                                TagService.viewTag(tagNum);
                            } else {
                                TagService.toggleViewTag(tagNum);
                            }
                        }
                    }
                }
            }
        }
    }

    QuickMenu {
        popupLayer: workspaceDots.popupLayer
        menuOpen: workspaceDots.menuOpen
        anchorX: workspaceDots.popupX
        anchorY: workspaceDots.popupY
        onCloseRequested: workspaceDots.menuOpen = false
    }
}
