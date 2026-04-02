import QtQuick
import QtQuick.Layouts
import PyShell.Services 1.0

Rectangle {
    id: mediaDetails

    property Item popupLayer: null
    property bool menuOpen: false
    property real anchorX: 0
    property real anchorY: 0

    signal closeRequested()

    parent: mediaDetails.popupLayer
    visible: opacity > 0
    opacity: mediaDetails.menuOpen ? 1.0 : 0.0
    x: mediaDetails.anchorX
    y: mediaDetails.anchorY

    width: Theme.mediaCardWidth
    property int contentMargin: Theme.spacingLG

    color: Theme.menuBg
    radius: Theme.menuRadius
    border.color: Theme.menuBorder
    border.width: 1

    property real slideOffset: mediaDetails.menuOpen ? 0 : -12
    transform: Translate { y: mediaDetails.slideOffset }
    Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
    Behavior on opacity    { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

    ColumnLayout {
        id: contentColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.spacingLG
        spacing: Theme.spacingMD

        RowLayout {
            spacing: Theme.spacingMD
            Layout.fillWidth: true

            Rectangle {
                width: 80
                height: 80
                radius: 8
                color: Theme.containerBg
                clip: true

                Image {
                    anchors.fill: parent
                    source: MediaService.artUrl
                    fillMode: Image.PreserveAspectCrop
                    visible: source != ""
                }

                Text {
                    anchors.centerIn: parent
                    text: "\uf001"
                    font.family: Theme.iconFont
                    font.pixelSize: 32
                    color: Theme.textColor
                    opacity: 0.2
                    visible: MediaService.artUrl == ""
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: MediaService.title
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 16
                    font.weight: Font.Bold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Text {
                    text: MediaService.artist
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 14
                    opacity: 0.7
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingXS

            SmoothSlider {
                id: seekBar
                Layout.fillWidth: true
                value: MediaService.length > 0 ? MediaService.position / MediaService.length : 0
                onReleased: v => MediaService.seekTo(v * MediaService.length)
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: MediaService.formatTime(seekBar.displayValue * MediaService.length)
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    opacity: 0.6
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: MediaService.formatTime(MediaService.length)
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    opacity: 0.6
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.spacingXL

            Rectangle {
                width: 40; height: 40
                radius: 20
                color: prevArea.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg

                MouseArea {
                    id: prevArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: MediaService.previous()
                    cursorShape: Qt.PointingHandCursor

                    Text {
                        anchors.centerIn: parent
                        text: Theme.iconPrev
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: 20
                    }
                }
            }

            Rectangle {
                width: 54; height: 54
                radius: 27
                color: playArea.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg

                MouseArea {
                    id: playArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: MediaService.togglePlay()
                    cursorShape: Qt.PointingHandCursor

                    Text {
                        anchors.centerIn: parent
                        text: MediaService.isPlaying ? Theme.iconPause : Theme.iconPlay
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: 24
                    }
                }
            }

            Rectangle {
                width: 40; height: 40
                radius: 20
                color: nextArea.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg

                MouseArea {
                    id: nextArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: MediaService.next()
                    cursorShape: Qt.PointingHandCursor

                    Text {
                        anchors.centerIn: parent
                        text: Theme.iconNext
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: 20
                    }
                }
            }
        }

        // Other active media sources
        ColumnLayout {
            Layout.fillWidth: true
            visible: othersRepeater.count > 0
            spacing: Theme.spacingSM

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: Theme.menuBorder
                opacity: 0.5
            }

            Text {
                text: "Other active media sources"
                color: Theme.textColor
                font.family: Theme.monoFont
                font.pixelSize: 12
                opacity: 0.6
            }

            Repeater {
                id: othersRepeater
                model: {
                    var others = [];
                    var all = MediaService.allPlayers;
                    var sel = MediaService.selectedPlayer;
                    for (var i = 0; i < all.length; i++) {
                        if (all[i].name !== sel) others.push(all[i]);
                    }
                    return others;
                }

                delegate: Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: compactCardLayout.implicitHeight + Theme.spacingSM * 2
                    radius: Theme.containerRadius
                    color: Theme.containerBg
                    border.color: Theme.menuBorder
                    border.width: 1

                    MouseArea {
                        anchors.fill: parent
                        onClicked: MediaService.selectPlayer(modelData.name)
                        cursorShape: Qt.PointingHandCursor
                    }

                    ColumnLayout {
                        id: compactCardLayout
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingSM
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingSM

                            Rectangle {
                                width: 44; height: 44
                                radius: 6
                                color: Theme.containerBg
                                clip: true
                                Image {
                                    anchors.fill: parent
                                    source: modelData.artUrl || ""
                                    fillMode: Image.PreserveAspectCrop
                                    visible: source !== ""
                                }
                                Text {
                                    anchors.centerIn: parent
                                    text: "\uf001"
                                    font.family: Theme.iconFont
                                    font.pixelSize: 18
                                    color: Theme.textColor
                                    opacity: 0.2
                                    visible: (modelData.artUrl || "") === ""
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: modelData.title || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 13
                                    font.weight: Font.Bold
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: modelData.artist || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 11
                                    opacity: 0.7
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    height: Math.max(Theme.mediaCardHeight, contentColumn.implicitHeight + Theme.spacingLG * 2)
}
