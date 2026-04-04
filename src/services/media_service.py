"""MediaService — MPRIS D-Bus media player control."""

import threading
import asyncio
import os

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

try:
    from dbus_next.aio import MessageBus
    from dbus_next import Variant, BusType
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class MediaService(QObject):
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = ""
        self._artist = ""
        self._album = ""
        self._art_url = ""
        self._is_playing = False
        self._has_media = False
        self._position = 0.0
        self._length = 0.0
        self._all_players = []
        self._selected_player = ""
        self._manual_selection = False
        self._players_metadata = {}
        self._seeking = False

        if HAS_DBUS:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(2000)
            self._poll_timer.timeout.connect(self._poll)
            self._poll_timer.start()
            self._poll()

        # Smooth position increment
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(1000)
        self._pos_timer.timeout.connect(self._tick_position)
        self._pos_timer.start()

    def _tick_position(self):
        if self._is_playing and not self._seeking and self._position < self._length:
            self._position += 1.0
            self.positionChanged.emit()

    def _poll(self):
        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_poll())
                loop.close()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    async def _async_poll(self):
        try:
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            introspection = await bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
            proxy = bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", introspection)
            iface = proxy.get_interface("org.freedesktop.DBus")
            names = await iface.call_list_names()

            mpris_names = [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]

            players_data = []
            for name in mpris_names:
                try:
                    intro = await bus.introspect(name, "/org/mpris/MediaPlayer2")
                    player_proxy = bus.get_proxy_object(name, "/org/mpris/MediaPlayer2", intro)
                    player_iface = player_proxy.get_interface("org.mpris.MediaPlayer2.Player")
                    props_iface = player_proxy.get_interface("org.freedesktop.DBus.Properties")

                    metadata = await props_iface.call_get("org.mpris.MediaPlayer2.Player", "Metadata")
                    status = await props_iface.call_get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
                    position = await props_iface.call_get("org.mpris.MediaPlayer2.Player", "Position")

                    md = self._unpack_variant(metadata)
                    title = md.get("xesam:title", "")
                    artist_val = md.get("xesam:artist", [])
                    artist = artist_val[0] if isinstance(artist_val, list) and artist_val else str(artist_val) if artist_val else ""
                    album = md.get("xesam:album", "")
                    art_url = md.get("mpris:artUrl", "")
                    length_us = md.get("mpris:length", 0)
                    if isinstance(length_us, Variant):
                        length_us = length_us.value
                    length = float(length_us) / 1_000_000.0 if length_us else 0.0

                    status_val = self._unpack_variant(status)
                    is_playing = status_val == "Playing"

                    pos_val = self._unpack_variant(position)
                    pos = float(pos_val) / 1_000_000.0 if pos_val else 0.0

                    players_data.append({
                        "name": name,
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "artUrl": art_url,
                        "isPlaying": is_playing,
                        "position": pos,
                        "length": length,
                        "status": status_val,
                    })
                except Exception:
                    continue

            bus.disconnect()
            self._update_from_poll(players_data)
        except Exception:
            pass

    def _unpack_variant(self, v):
        if isinstance(v, Variant):
            return self._unpack_variant(v.value)
        if isinstance(v, dict):
            return {k: self._unpack_variant(val) for k, val in v.items()}
        if isinstance(v, list):
            return [self._unpack_variant(item) for item in v]
        return v

    def _update_from_poll(self, players_data):
        player_names = [p["name"] for p in players_data]

        if player_names != self._all_players:
            self._all_players = player_names
            self.allPlayersChanged.emit()

        self._players_metadata = {p["name"]: p for p in players_data}

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
        if not self._seeking and abs(position - self._position) > 2.0:
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

    def _mpris_command(self, player_name, method):
        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_command(player_name, method))
                loop.close()
            except Exception:
                pass
            self._poll()
        threading.Thread(target=_run, daemon=True).start()

    async def _async_command(self, player_name, method):
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        intro = await bus.introspect(player_name, "/org/mpris/MediaPlayer2")
        proxy = bus.get_proxy_object(player_name, "/org/mpris/MediaPlayer2", intro)
        iface = proxy.get_interface("org.mpris.MediaPlayer2.Player")
        await getattr(iface, method)()
        bus.disconnect()

    @Slot()
    def togglePlay(self):
        player = self._selected_player or (self._all_players[0] if self._all_players else "")
        if player:
            self._mpris_command(player, "call_play_pause")

    @Slot()
    def next(self):
        player = self._selected_player or (self._all_players[0] if self._all_players else "")
        if player:
            self._mpris_command(player, "call_next")

    @Slot()
    def previous(self):
        player = self._selected_player or (self._all_players[0] if self._all_players else "")
        if player:
            self._mpris_command(player, "call_previous")

    @Slot(float)
    def seekTo(self, seconds):
        if not self._selected_player:
            return
        self._seeking = True
        self._position = max(0, min(seconds, self._length))
        self.positionChanged.emit()

        player_name = self._selected_player
        target_us = int(self._position * 1_000_000)

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_seek(player_name, target_us))
                loop.close()
            except Exception:
                pass
            self._seeking = False
        threading.Thread(target=_run, daemon=True).start()

    async def _async_seek(self, player_name, position_us):
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        intro = await bus.introspect(player_name, "/org/mpris/MediaPlayer2")
        proxy = bus.get_proxy_object(player_name, "/org/mpris/MediaPlayer2", intro)
        props_iface = proxy.get_interface("org.freedesktop.DBus.Properties")
        cur_pos = await props_iface.call_get("org.mpris.MediaPlayer2.Player", "Position")
        cur_us = self._unpack_variant(cur_pos) or 0
        iface = proxy.get_interface("org.mpris.MediaPlayer2.Player")
        await iface.call_seek(position_us - int(cur_us))
        bus.disconnect()

    @Slot(str)
    def selectPlayer(self, name):
        if name in self._all_players:
            self._selected_player = name
            self._manual_selection = True
            self.selectedPlayerChanged.emit()
            data = self._players_metadata.get(name, {})
            self._set_props(data)

    @Slot(str, result=str)
    def formatTime(self, total_seconds):
        try:
            total = float(total_seconds)
        except (ValueError, TypeError):
            return "0:00"
        if total < 0:
            return "0:00"
        minutes = int(total // 60)
        seconds = int(total % 60)
        return f"{minutes}:{seconds:02d}"
