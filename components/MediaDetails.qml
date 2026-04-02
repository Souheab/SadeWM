import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import Quickshell
import ".."
import "../services"

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
    // Compute height from content so popup never clips its children
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

        // Album Art & Info
        RowLayout {
            spacing: Theme.spacingMD
            Layout.fillWidth: true

            // Album Art Placeholder or Image
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

            // Info
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

        // Progress Bar & Time Labels
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
                    id: currentTimeLabel
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

        // Controls
        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.spacingXL

            // Prev
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

            // Play/Pause
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

            // Next
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

            // Divider
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
                        if (all[i] !== sel) others.push(all[i]);
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

                    // Background click-to-select (non-button areas)
                    MouseArea {
                        anchors.fill: parent
                        onClicked: MediaService.selectPlayer(modelData)
                        cursorShape: Qt.PointingHandCursor
                    }

                    ColumnLayout {
                        id: compactCardLayout
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingSM
                        spacing: 4

                        // Thumbnail + Title/Artist + Controls
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
                                    source: modelData.trackArtUrl || modelData.metadata["mpris:artUrl"] || ""
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
                                    visible: (modelData.trackArtUrl || modelData.metadata["mpris:artUrl"] || "") === ""
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: modelData.trackTitle || modelData.metadata["xesam:title"] || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 13
                                    font.weight: Font.Bold
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: modelData.trackArtist || (Array.isArray(modelData.metadata["xesam:artist"]) ? modelData.metadata["xesam:artist"][0] : modelData.metadata["xesam:artist"]) || "Unknown"
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 11
                                    opacity: 0.7
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }

                            RowLayout {
                                spacing: 6
                                Rectangle {
                                    width: 28; height: 28; radius: 14
                                    color: cpPrev.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg
                                    MouseArea {
                                        id: cpPrev
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: function(mouse) { mouse.accepted = true; modelData.previous(); }
                                    }
                                    Text { anchors.centerIn: parent; text: Theme.iconPrev; color: Theme.textColor; font.family: Theme.iconFont; font.pixelSize: 12 }
                                }
                                Rectangle {
                                    width: 34; height: 34; radius: 17
                                    color: cpPlay.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg
                                    MouseArea {
                                        id: cpPlay
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: function(mouse) { mouse.accepted = true; modelData.togglePlaying(); }
                                    }
                                    Text { anchors.centerIn: parent; text: modelData.playbackState === 1 ? Theme.iconPause : Theme.iconPlay; color: Theme.textColor; font.family: Theme.iconFont; font.pixelSize: 14 }
                                }
                                Rectangle {
                                    width: 28; height: 28; radius: 14
                                    color: cpNext.containsMouse ? Theme.buttonHoverBg : Theme.buttonBg
                                    MouseArea {
                                        id: cpNext
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: function(mouse) { mouse.accepted = true; modelData.next(); }
                                    }
                                    Text { anchors.centerIn: parent; text: Theme.iconNext; color: Theme.textColor; font.family: Theme.iconFont; font.pixelSize: 12 }
                                }
                            }
                        }

                        // Progress bar + time labels
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            Rectangle {
                                Layout.fillWidth: true
                                height: 3
                                radius: 1
                                color: Theme.mediaProgressTrackBg
                                property real ratio: (modelData.length > 0) ? Math.min(1, modelData.position / modelData.length) : 0

                                Rectangle {
                                    anchors.left: parent.left
                                    width: parent.width * parent.ratio
                                    height: parent.height
                                    radius: 1
                                    color: Theme.mediaProgressColor
                                    Behavior on width { NumberAnimation { duration: 100 } }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    anchors.topMargin: -4
                                    anchors.bottomMargin: -4
                                    cursorShape: Qt.PointingHandCursor
                                    onReleased: function(mouse) {
                                        var ratio = Math.max(0, Math.min(1, mouse.x / parent.width));
                                        MediaService.seekTo(ratio * modelData.length, modelData);
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: MediaService.formatTime(modelData.position)
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 10
                                    opacity: 0.6
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: MediaService.formatTime(modelData.length)
                                    color: Theme.textColor
                                    font.family: Theme.monoFont
                                    font.pixelSize: 10
                                    opacity: 0.6
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

