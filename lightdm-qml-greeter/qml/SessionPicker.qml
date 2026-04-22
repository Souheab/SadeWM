import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Sadewm

// A compact pill-shaped popup session picker.  Pressing the pill opens
// a dropdown of all local sessions reported by LightDM; the selection
// is stored in ``selectedKey`` and announced via ``sessionChanged``.
Item {
    id: root

    // Key (session id) currently selected.  Empty means "use the
    // default session hint from the daemon".
    property string selectedKey: greeter.defaultSession
    property string selectedName: ""

    signal sessionChanged(string key)

    implicitHeight: pill.implicitHeight
    implicitWidth:  pill.implicitWidth

    function _updateNameFromKey() {
        for (var i = 0; i < sessionsModel.rowCount(null); ++i) {
            var idx = sessionsModel.index(i, 0);
            var key = sessionsModel.data(idx, 0x0100 /* KeyRole */);
            if (key === root.selectedKey) {
                root.selectedName = sessionsModel.data(idx, 0 /* DisplayRole */);
                return;
            }
        }
        root.selectedName = root.selectedKey;
    }

    Component.onCompleted: _updateNameFromKey()

    PillButton {
        id: pill
        text: root.selectedName.length ? root.selectedName : "Session"
        iconText: "\uf108"
        onClicked: menu.open()
    }

    Menu {
        id: menu
        y: pill.height + Sadewm.Theme.spacingXS

        background: Rectangle {
            color: Sadewm.Theme.containerBg
            border.color: Sadewm.Theme.menuBorder
            border.width: 1
            radius: Sadewm.Theme.containerRadius
        }

        Repeater {
            model: sessionsModel
            delegate: MenuItem {
                text: model.display
                contentItem: Text {
                    text: parent.text
                    color: Sadewm.Theme.textColor
                    font.family: Sadewm.Theme.uiFont
                    font.pixelSize: Sadewm.Theme.bodySize
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: Sadewm.Theme.spacingMD
                    rightPadding: Sadewm.Theme.spacingMD
                }
                background: Rectangle {
                    color: parent.highlighted ? Sadewm.Theme.menuHover
                                              : "transparent"
                    radius: Sadewm.Theme.containerRadius - 4
                }
                onTriggered: {
                    root.selectedKey  = model.key;
                    root.selectedName = model.display;
                    root.sessionChanged(model.key);
                }
            }
        }
    }
}
