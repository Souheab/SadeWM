import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Sadewm

// The centerpiece: a rounded Tokyo-Night card with the hostname, the
// username / password flow, status messages and a "Log in" action.
Rectangle {
    id: card

    // The bridge dispatches prompts (password / pam questions) to us
    // and receives the final response.  We keep the flow deliberately
    // small: pick user -> type response to each prompt -> start
    // session.
    property string currentUser: ""
    property string selectedSession: ""
    property string statusMessage: ""
    property bool   statusIsError: false
    property bool   busy: false

    signal loginSucceeded()

    color: Sadewm.Theme.containerBg
    radius: Sadewm.Theme.cardRadius
    border.color: Sadewm.Theme.menuBorder
    border.width: 1
    implicitWidth:  Sadewm.Theme.cardWidth
    implicitHeight: layout.implicitHeight + Sadewm.Theme.spacingXL * 2

    // ── Helpers ────────────────────────────────────────────────────
    function beginLogin(username) {
        card.currentUser = username;
        card.statusMessage = "";
        card.busy = true;
        bridge.authenticate(username);
    }

    function submit() {
        if (!bridge.awaitingResponse) {
            // No outstanding prompt — user just pressed enter on an
            // empty state.  Start authentication with whatever's in
            // the username field.
            beginLogin(usernameField.text.trim());
            return;
        }
        card.busy = true;
        bridge.respond(passwordField.text);
        passwordField.text = "";
    }

    Connections {
        target: bridge
        function onPromptReceived(text, secret) {
            card.statusMessage = "";
            passwordField.placeholderText = text.length ? text
                : (secret ? "Password" : "Response");
            passwordField.echoMode = secret ? TextInput.Password
                                            : TextInput.Normal;
            passwordField.enabled = true;
            passwordField.forceActiveFocus();
            card.busy = false;
        }
        function onMessageReceived(text, error) {
            card.statusMessage = text;
            card.statusIsError = error;
        }
        function onAuthenticationComplete(success) {
            card.busy = false;
            if (success) {
                card.statusMessage = "Starting session\u2026";
                card.statusIsError = false;
                const key = card.selectedSession.length
                    ? card.selectedSession
                    : greeter.defaultSession;
                if (!bridge.startSession(key)) {
                    card.statusMessage = "Failed to start session";
                    card.statusIsError = true;
                }
                card.loginSucceeded();
            } else {
                card.statusMessage = "Authentication failed";
                card.statusIsError = true;
                passwordField.text = "";
                // Restart so the daemon will issue a fresh password
                // prompt.
                bridge.authenticate(card.currentUser);
            }
        }
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Sadewm.Theme.spacingXL
        spacing: Sadewm.Theme.spacingLG

        // ── Greeting ──
        ColumnLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: Sadewm.Theme.spacingXS

            Text {
                text: "Welcome"
                color: Sadewm.Theme.textColor
                font.family: Sadewm.Theme.uiFont
                font.pixelSize: Sadewm.Theme.titleSize
                font.weight: Font.DemiBold
                Layout.alignment: Qt.AlignHCenter
            }
            Text {
                text: bridge.hostname.length ? bridge.hostname : "sadewm"
                color: Sadewm.Theme.textMuted
                font.family: Sadewm.Theme.monoFont
                font.pixelSize: Sadewm.Theme.smallSize
                Layout.alignment: Qt.AlignHCenter
            }
        }

        // ── Username field ──
        Rectangle {
            Layout.fillWidth: true
            height: Sadewm.Theme.inputHeight
            radius: Sadewm.Theme.containerRadius
            color: Sadewm.Theme.background
            border.color: usernameField.activeFocus ? Sadewm.Theme.accent
                                                    : Sadewm.Theme.menuBorder
            border.width: 1

            TextField {
                id: usernameField
                anchors.fill: parent
                anchors.leftMargin: Sadewm.Theme.spacingMD
                anchors.rightMargin: Sadewm.Theme.spacingMD
                placeholderText: "Username"
                color: Sadewm.Theme.textColor
                placeholderTextColor: Sadewm.Theme.textMuted
                font.family: Sadewm.Theme.uiFont
                font.pixelSize: Sadewm.Theme.bodySize
                background: null
                text: greeter.selectUser
                enabled: !bridge.awaitingResponse && !card.busy
                onAccepted: {
                    if (text.trim().length)
                        card.beginLogin(text.trim());
                }
                Keys.onTabPressed: passwordField.forceActiveFocus()
            }
        }

        // ── Password / prompt field ──
        Rectangle {
            Layout.fillWidth: true
            height: Sadewm.Theme.inputHeight
            radius: Sadewm.Theme.containerRadius
            color: Sadewm.Theme.background
            border.color: passwordField.activeFocus ? Sadewm.Theme.accent
                                                    : Sadewm.Theme.menuBorder
            border.width: 1

            TextField {
                id: passwordField
                anchors.fill: parent
                anchors.leftMargin: Sadewm.Theme.spacingMD
                anchors.rightMargin: Sadewm.Theme.spacingMD
                placeholderText: "Password"
                echoMode: TextInput.Password
                color: Sadewm.Theme.textColor
                placeholderTextColor: Sadewm.Theme.textMuted
                font.family: Sadewm.Theme.uiFont
                font.pixelSize: Sadewm.Theme.bodySize
                background: null
                enabled: bridge.awaitingResponse && !card.busy
                onAccepted: card.submit()
            }
        }

        // ── Status line (errors / info from PAM) ──
        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: Sadewm.Theme.bodySize + 6
            text: card.statusMessage
            color: card.statusIsError ? Sadewm.Theme.danger
                                      : Sadewm.Theme.textMuted
            font.family: Sadewm.Theme.uiFont
            font.pixelSize: Sadewm.Theme.smallSize
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        // ── Action row ──
        RowLayout {
            Layout.fillWidth: true
            spacing: Sadewm.Theme.spacingSM

            SessionPicker {
                id: sessionPicker
                onSessionChanged: (key) => card.selectedSession = key
            }

            Item { Layout.fillWidth: true }

            PillButton {
                text: card.busy ? "\u2026" : "Log in"
                highlighted: true
                onClicked: card.submit()
            }
        }
    }
}
