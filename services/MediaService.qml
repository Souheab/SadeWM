pragma Singleton

import Quickshell
import Quickshell.Services.Mpris
import QtQuick

Singleton {
    id: root

    // Reference to the active player (most recently playing)
    property var activePlayer: null
    property var selectedPlayer: null
    property bool manualSelection: false

    // One-list of all known players and currently selected player for UI control
    readonly property list<var> allPlayers: Mpris.players.values

    // Exposed properties for easy binding
    readonly property string title: selectedPlayer ? (selectedPlayer.trackTitle || selectedPlayer.metadata["xesam:title"] || "Unknown Title") : ""
    readonly property string artist: selectedPlayer ? (selectedPlayer.trackArtist || (Array.isArray(selectedPlayer.metadata["xesam:artist"]) ? selectedPlayer.metadata["xesam:artist"][0] : selectedPlayer.metadata["xesam:artist"]) || "Unknown Artist") : ""
    readonly property string album: selectedPlayer ? (selectedPlayer.trackAlbum || selectedPlayer.metadata["xesam:album"] || "") : ""
    readonly property string artUrl: selectedPlayer ? (selectedPlayer.trackArtUrl || selectedPlayer.metadata["mpris:artUrl"] || "") : ""
    readonly property bool isPlaying: selectedPlayer ? selectedPlayer.playbackState === 1 : false
    readonly property bool hasMedia: selectedPlayer !== null && title !== ""

    // Live position tracking
    property real position: 0
    property real length: activePlayer ? (activePlayer.length || 0) : 0
    property bool seeking: false

    // Sync position when the player's reported position changes or media changes
    Connections {
        target: activePlayer
        function onPositionChanged() {
            if (activePlayer && !root.seeking) root.position = activePlayer.position;
            if (activePlayer) root.length = activePlayer.length || 0;
        }
    }

    onActivePlayerChanged: {
        if (activePlayer) {
            root.position = activePlayer.position;
            root.length = activePlayer.length || 0;
        } else {
            root.position = 0;
            root.length = 0;
        }
    }

    // Smooth position timer for live updates between D-Bus reports
    Timer {
        interval: 1000
        running: root.isPlaying && !root.seeking
        repeat: true
        onTriggered: {
            if (root.position < root.length) {
                root.position += 1;
            }
        }
    }

    function seekTo(seconds, player) {
        var targetPlayer = player || root.selectedPlayer || root.activePlayer;
        if (!targetPlayer || isNaN(seconds)) return;

        var length = targetPlayer.length || root.length || 0;
        var clamped = Math.max(0, Math.min(seconds, length));
        var targetMicros = Math.round(clamped * 1000000);

        root.seeking = true;

        if ("position" in targetPlayer) {
            targetPlayer.position = clamped;
        } else if (typeof targetPlayer.setPosition === "function" && targetPlayer.metadata && targetPlayer.metadata["mpris:trackid"]) {
            targetPlayer.setPosition(targetPlayer.metadata["mpris:trackid"], targetMicros);
        } else if (typeof targetPlayer.seek === "function") {
            var currentMicros = Math.round((targetPlayer.position || root.position) * 1000000);
            targetPlayer.seek(targetMicros - currentMicros);
        }

        if (targetPlayer === root.selectedPlayer) {
            root.position = clamped;
            root.length = length;
        }

        Qt.callLater(function() {
            root.seeking = false;
        });
    }

    // Utility: Format seconds into MM:SS
    function formatTime(totalSeconds) {
        if (isNaN(totalSeconds) || totalSeconds < 0) return "0:00";
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = Math.floor(totalSeconds % 60);
        return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
    }

    // Control functions (use selected player for UI controls)
    function togglePlay() {
        const player = root.selectedPlayer || root.activePlayer;
        if (player) player.togglePlaying();
    }

    function next() {
        const player = root.selectedPlayer || root.activePlayer;
        if (player && player.canGoNext) player.next();
    }

    function previous() {
        const player = root.selectedPlayer || root.activePlayer;
        if (player && player.canGoPrevious) player.previous();
    }

    function selectPlayer(player) {
        if (!player) return;
        root.selectedPlayer = player;
        root.manualSelection = true;
    }

    function clearSelection() {
        root.selectedPlayer = root.activePlayer;
        root.manualSelection = false;
    }

    // Automatically pick the player that is actually playing if multiple exist
    readonly property var _players: Mpris.players.values
    on_PlayersChanged: updateActivePlayer()

    function updateActivePlayer() {
        let players = Mpris.players.values;
        if (players.length === 0) {
            root.activePlayer = null;
            root.selectedPlayer = null;
            return;
        }

        // Prefer one that is currently playing (playbackState 1)
        let found = null;
        for (let i = 0; i < players.length; i++) {
            let player = players[i];
            if (player && player.playbackState === 1) {
                found = player;
                break;
            }
        }

        if (!found) {
            found = players[0];
        }

        root.activePlayer = found;

        if (!root.manualSelection || !root.selectedPlayer || !players.includes(root.selectedPlayer)) {
            root.selectedPlayer = found;
            root.manualSelection = false;
        }
    }

    Component.onCompleted: updateActivePlayer()
}
