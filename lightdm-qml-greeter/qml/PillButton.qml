import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Sadewm

// Rounded pill-style button used for power actions and the session
// picker.  Mirrors the "container" rectangles used throughout
// sadeshell's bar/menu components.
Item {
    id: root

    property string text: ""
    property string iconText: ""     // Nerd-Font glyph, optional
    property bool   danger: false
    property bool   highlighted: false
    property alias  mouseArea: area

    signal clicked()

    implicitHeight: 36
    implicitWidth:  Math.max(label.implicitWidth + iconLabel.implicitWidth
                             + Sadewm.Theme.spacingLG * 2
                             + (iconLabel.visible ? Sadewm.Theme.spacingSM : 0),
                             96)

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: Sadewm.Theme.pillRadius
        color: root.highlighted
               ? Sadewm.Theme.accent
               : (area.containsMouse
                  ? Sadewm.Theme.buttonHover
                  : Sadewm.Theme.buttonBg)
        border.width: 1
        border.color: root.danger ? Sadewm.Theme.danger : Sadewm.Theme.menuBorder
        Behavior on color { ColorAnimation { duration: Sadewm.Theme.animFast } }
    }

    Row {
        anchors.centerIn: parent
        spacing: Sadewm.Theme.spacingSM

        Text {
            id: iconLabel
            visible: root.iconText.length > 0
            text: root.iconText
            color: root.highlighted ? Sadewm.Theme.background
                                    : (root.danger ? Sadewm.Theme.danger
                                                   : Sadewm.Theme.textColor)
            font.family: "FiraCode Nerd Font"
            font.pixelSize: 14
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: label
            text: root.text
            color: root.highlighted ? Sadewm.Theme.background
                                    : Sadewm.Theme.textColor
            font.family: Sadewm.Theme.uiFont
            font.pixelSize: Sadewm.Theme.bodySize
            verticalAlignment: Text.AlignVCenter
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
