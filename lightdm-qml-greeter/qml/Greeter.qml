import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Sadewm

// Root greeter window.  Fullscreen, undecorated, Tokyo-Night
// background, with a clock in the top-left, power buttons in the
// top-right and a centered login card.
Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    flags: Qt.FramelessWindowHint
    color: Sadewm.Theme.background
    title: "sadewm greeter"

    // Soft radial gradient backdrop to give the flat Tokyo-Night base
    // a little depth without introducing any extra assets.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#1a1b26" }
            GradientStop { position: 1.0; color: "#16161e" }
        }
    }

    // Subtle accent glow behind the card.
    Rectangle {
        anchors.centerIn: parent
        width:  parent.width  * 0.55
        height: parent.height * 0.55
        radius: width / 2
        opacity: 0.15
        color: Sadewm.Theme.accent
        visible: true
    }

    // ── Top-left: clock ──
    ColumnLayout {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.topMargin: Sadewm.Theme.spacingXL
        anchors.leftMargin: Sadewm.Theme.spacingXL
        spacing: Sadewm.Theme.spacingXS

        Text {
            id: timeLabel
            color: Sadewm.Theme.textColor
            font.family: Sadewm.Theme.uiFont
            font.pixelSize: 42
            font.weight: Font.Light
        }
        Text {
            id: dateLabel
            color: Sadewm.Theme.textMuted
            font.family: Sadewm.Theme.uiFont
            font.pixelSize: Sadewm.Theme.bodySize
        }
        Timer {
            interval: 1000
            running: true
            repeat: true
            triggeredOnStart: true
            onTriggered: {
                const now = new Date();
                timeLabel.text = Qt.formatTime(now, "hh:mm");
                dateLabel.text = Qt.formatDate(now, "dddd, d MMMM yyyy");
            }
        }
    }

    // ── Top-right: power buttons ──
    PowerButtons {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: Sadewm.Theme.spacingXL
        anchors.rightMargin: Sadewm.Theme.spacingXL
    }

    // ── Centered login card ──
    LoginCard {
        id: loginCard
        anchors.centerIn: parent
    }

    // Keyboard shortcut: Escape cancels any in-flight authentication.
    Shortcut {
        sequence: "Escape"
        onActivated: bridge.cancel()
    }

    Component.onCompleted: {
        // Autologin path – the daemon may tell us to log a user in
        // without ever showing the UI.
        if (greeter.selectUser.length && greeter.autologinTimeout === 0) {
            // nothing: user field will be prefilled, prompt flow will
            // start when the user presses enter.
        }
    }
}
