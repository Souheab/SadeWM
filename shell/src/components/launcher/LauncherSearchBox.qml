import QtQuick
import "../../shared"

// LauncherSearchBox: a reusable search bar used by AppLauncher and EmojiPicker.
// The parent window is expected to expose:
//   property string placeholderText
//   property string iconGlyph     (FontAwesome glyph for the leading icon)
// Emits:
//   signal textChanged(string text)       — debounced
//   signal accepted()                     — Enter pressed
//   signal nextItem()                     — Down / Ctrl+J
//   signal prevItem()                     — Up / Ctrl+K
//   signal dismissed()                    — Escape

Item {
    id: root

    property string placeholderText: "Search\u2026"
    property string iconGlyph: "\uf002"
    property alias text: searchField.text

    signal queryChanged(string text)
    signal accepted()
    signal nextItem()
    signal prevItem()
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
            anchors.rightMargin: 20
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
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        root.accepted()
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
    }

    Timer {
        id: debounce
        interval: 30
        onTriggered: root.queryChanged(searchField.text)
    }
}
