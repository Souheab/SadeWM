"""MPRIS state subscriptions; only the selected playing player is corrected."""
import time
from PySide6.QtCore import Property, Signal, Slot, QTimer
from ..shared.async_bus import AsyncService
from ..shared.mpris_monitor import MprisMonitor

class MediaService(AsyncService):
    titleChanged = Signal()
    artistChanged = Signal()
    albumChanged = Signal()
    artUrlChanged = Signal()
    isPlayingChanged = Signal()
    hasMediaChanged = Signal()
    positionChanged = Signal()
    lengthChanged = Signal()
    allPlayersChanged = Signal()
    selectedPlayerChanged = Signal()

    def __init__(self, parent=None, worker=None):
        super().__init__(parent, worker)
        self._title = self._artist = self._album = self._art_url = ""
        self._is_playing = self._has_media = False
        self._position = self._length = self._anchor_position = 0.0
        self._anchor = time.monotonic()
        self._rate = 1
        self._all_players = []
        self._selected_player = ""
        self._manual_selection = False
        self._players_metadata = {}
        self.monitor = MprisMonitor(self)
        self.start_task(self.monitor.run())
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(1000)
        self._pos_timer.timeout.connect(self._tick_position)
        self._pos_timer.start()

    def _tick_position(self):
        if self._is_playing:
            self._position = max(0, self._anchor_position + (time.monotonic() - self._anchor) * self._rate)
            if self._length > 0:
                self._position = min(self._position, self._length)
            self.positionChanged.emit()

    def stop(self):
        self._pos_timer.stop()
        super().stop()

    def apply_state(self, players_data):
        player_names = [p["name"] for p in players_data]

        if players_data != list(self._players_metadata.values()):
            self._all_players = player_names

        self._players_metadata = {p["name"]: p for p in players_data}
        self.allPlayersChanged.emit()

        # Pick active player
        selected = self._selected_player
        if self._manual_selection and selected in player_names:
            pass
        else:
            # Prefer playing player
            playing = [p for p in players_data if p["isPlaying"]]
            if playing:
                selected = playing[0]["name"]
            elif players_data:
                selected = players_data[0]["name"]
            else:
                selected = ""
            self._manual_selection = False

        if selected != self._selected_player:
            self._selected_player = selected
            self.selectedPlayerChanged.emit()

        data = self._players_metadata.get(selected, {})
        self._set_props(data)
        self.worker.loop.call_soon_threadsafe(setattr, self.monitor, "selected", selected)

    def _set_props(self, data):
        title = data.get("title", "")
        artist = data.get("artist", "")
        album = data.get("album", "")
        art_url = data.get("artUrl", "")
        is_playing = data.get("isPlaying", False)
        position = data.get("position", 0.0)
        length = data.get("length", 0.0)
        has_media = bool(title)

        if title != self._title:
            self._title = title
            self.titleChanged.emit()
        if artist != self._artist:
            self._artist = artist
            self.artistChanged.emit()
        if album != self._album:
            self._album = album
            self.albumChanged.emit()
        if art_url != self._art_url:
            self._art_url = art_url
            self.artUrlChanged.emit()
        if is_playing != self._is_playing:
            self._is_playing = is_playing
            self.isPlayingChanged.emit()
        if has_media != self._has_media:
            self._has_media = has_media
            self.hasMediaChanged.emit()
        self._anchor = time.monotonic()
        self._anchor_position = position
        self._rate = data.get("rate", 1)
        if position != self._position:
            self._position = position
            self.positionChanged.emit()
        if length != self._length:
            self._length = length
            self.lengthChanged.emit()

    @Property(str, notify=titleChanged)
    def title(self):
        return self._title

    @Property(str, notify=artistChanged)
    def artist(self):
        return self._artist

    @Property(str, notify=albumChanged)
    def album(self):
        return self._album

    @Property(str, notify=artUrlChanged)
    def artUrl(self):
        return self._art_url

    @Property(bool, notify=isPlayingChanged)
    def isPlaying(self):
        return self._is_playing

    @Property(bool, notify=hasMediaChanged)
    def hasMedia(self):
        return self._has_media

    @Property(float, notify=positionChanged)
    def position(self):
        return self._position

    @Property(float, notify=lengthChanged)
    def length(self):
        return self._length

    @Property("QVariantList", notify=allPlayersChanged)
    def allPlayers(self):
        all_data = []
        for name in self._all_players:
            md = self._players_metadata.get(name, {})
            all_data.append({
                "name": name,
                "title": md.get("title", ""),
                "artist": md.get("artist", ""),
                "artUrl": md.get("artUrl", ""),
                "isPlaying": md.get("isPlaying", False),
                "position": md.get("position", 0.0),
                "length": md.get("length", 0.0),
            })
        return all_data

    @Property(str, notify=selectedPlayerChanged)
    def selectedPlayer(self):
        return self._selected_player


    def _command(self, method, signature="", body=()):
        name = self._selected_player
        data = self._players_metadata.get(name)
        if data:
            self.command(self.monitor.command(name, data["owner"], method, signature, body), name)

    @Slot()
    def togglePlay(self):
        self._command("PlayPause")

    @Slot()
    def next(self):
        self._command("Next")

    @Slot()
    def previous(self):
        self._command("Previous")

    @Slot(float)
    def seekTo(self, seconds):
        data = self._players_metadata.get(self._selected_player, {})
        track = data.get("track")
        if track and track != "/org/mpris/MediaPlayer2/TrackList/NoTrack":
            self.command(self.monitor.seek(self._selected_player, data["owner"], track,
                                           int(max(0, min(seconds, self._length)) * 1e6)), self._selected_player)

    @Slot(str)
    def selectPlayer(self, name):
        if name in self._all_players:
            self._selected_player = name
            self._manual_selection = True
            self.selectedPlayerChanged.emit()
            self._set_props(self._players_metadata[name])
            self.worker.loop.call_soon_threadsafe(self.monitor.select, name)

    @Slot(str, result=str)
    def formatTime(self, total_seconds):
        try:
            total = max(0, int(float(total_seconds)))
            return f"{total // 60}:{total % 60:02d}"
        except (ValueError, TypeError, OverflowError):
            return "0:00"
