import QtQuick
import "../shared"

// LauncherSearchBox: reusable search and keyboard navigation for launchers/pickers.
// The parent window is expected to expose:
//   property string placeholderText
//   property string iconGlyph     (FontAwesome glyph for the leading icon)
// Emits:
//   signal textChanged(string text)       — debounced
//   signal accepted()                     — Enter pressed
//   signal nextItem()                     — Down / Ctrl+J
//   signal prevItem()                     — Up / Ctrl+K
//   signal nextColumn()/prevColumn()       — Right / Left
//   signal nextLinear()/prevLinear()       — Tab / Shift+Tab
//   signal modifierReleased()              — Alt released
//   signal dismissed()                    — Escape

Item {
    id: root

    property string placeholderText: "Search\u2026"
    property string iconGlyph: "\uf002"
    property string hintText: ""
    property alias text: searchField.text

    signal queryChanged(string text)
    signal accepted()
    signal nextItem()
    signal prevItem()
    signal nextColumn()
    signal prevColumn()
    signal nextLinear()
    signal prevLinear()
    signal modifierReleased()
    signal dismissed()

    implicitHeight: 56

    function forceActiveFocus() {
        searchField.forceActiveFocus()
    }

    function clear() {
        searchField.text = ""
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"

        Row {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: hintLabel.visible
                ? hintLabel.implicitWidth + 36
                : 20
            spacing: 12

            Text {
                text: root.iconGlyph
                font.family: Theme.iconFont
                font.pixelSize: 18
                color: Theme.dotOccupied
                anchors.verticalCenter: parent.verticalCenter
            }

            TextInput {
                id: searchField
                width: parent.width - 50
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.textColor
                font.family: Theme.monoFont
                font.pixelSize: 15
                selectionColor: Theme.dotSelected
                selectedTextColor: Theme.barBg
                clip: true

                onTextChanged: debounce.restart()

                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Escape) {
                        root.dismissed()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Down ||
                                (event.key === Qt.Key_J && (event.modifiers & Qt.ControlModifier))) {
                        root.nextItem()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up ||
                                (event.key === Qt.Key_K && (event.modifiers & Qt.ControlModifier))) {
                        root.prevItem()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Right) {
                        root.nextColumn()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Left) {
                        root.prevColumn()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Tab &&
                               !(event.modifiers & Qt.ShiftModifier)) {
                        root.nextLinear()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Backtab ||
                               (event.key === Qt.Key_Tab &&
                                (event.modifiers & Qt.ShiftModifier))) {
                        root.prevLinear()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        root.accepted()
                        event.accepted = true
                    }
                }

                Keys.onReleased: (event) => {
                    if (event.key === Qt.Key_Alt) {
                        root.modifierReleased()
                        event.accepted = true
                    }
                }

                Text {
                    anchors.fill: parent
                    text: root.placeholderText
                    color: Theme.dotOccupied
                    font: parent.font
                    visible: searchField.text.length === 0
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Text {
            id: hintLabel
            anchors {
                right: parent.right
                rightMargin: 20
                verticalCenter: parent.verticalCenter
            }
            visible: root.hintText.length > 0 && root.width >= 680
            text: root.hintText
            color: Qt.alpha(Theme.textColor, 0.45)
            font.family: Theme.monoFont
            font.pixelSize: 10
        }
    }

    Timer {
        id: debounce
        interval: 30
        onTriggered: root.queryChanged(searchField.text)
    }
}
