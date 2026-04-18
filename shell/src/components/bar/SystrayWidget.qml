import QtQuick
import QtQuick.Controls
import PyShell.Services 1.0
import "../shared"

// SystrayWidget — shows StatusNotifier tray icons in the bar.
// Each icon is clickable (left = Activate, right = ContextMenu).
Rectangle {
    id: systrayWidget
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg
    visible: SystrayService.items.length > 0

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

                // Icon: prefer base64 encoded image, fall back to icon name via theme.
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
                        var item = iconBtn.modelData;
                        if (!item) return "";
                        if (item.iconBase64 && item.iconBase64 !== "")
                            return "data:image/png;base64," + item.iconBase64;
                        return "";
                    }
                }

                // Fallback text icon when no image is available
                Text {
                    anchors.centerIn: parent
                    visible: !iconImage.visible || iconImage.status !== Image.Ready
                    text: "\uf2d0"
                    font.family: Theme.iconFont
                    font.pixelSize: Theme.iconFontSize
                    color: Theme.textColor
                }

                ToolTip {
                    id: tooltip
                    visible: iconArea.containsMouse && iconBtn.modelData
                             && iconBtn.modelData.title !== ""
                    delay: 600
                    text: iconBtn.modelData ? (iconBtn.modelData.title || "") : ""

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
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton

                    onClicked: mouse => {
                        if (!iconBtn.modelData) return;
                        var item = iconBtn.modelData;
                        var pos = iconBtn.mapToGlobal(iconBtn.width / 2, iconBtn.height / 2);
                        if (mouse.button === Qt.RightButton)
                            SystrayService.contextMenu(item.id, pos.x, Theme.barHeight);
                        else
                            SystrayService.activate(item.id, pos.x, pos.y);
                    }
                }
            }
        }
    }

    width: systrayRow.width + Theme.containerPadding
}
