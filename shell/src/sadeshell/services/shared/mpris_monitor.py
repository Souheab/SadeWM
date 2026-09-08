"""Worker-owned MPRIS catalogue with monotonic playback anchors."""
import asyncio
import time

from dbus_next import BusType, MessageType
from .async_bus import DBUS, PROPS, call, unpack

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


class MprisMonitor:
    def __init__(self, service):
        self.service = service
        self.players = {}
        self.selected = ""
        self.bus = None
        self.revision = 0
        self.owners = {}

    def select(self, name):
        self.selected = name
        self.emit()

    async def add(self, name, owner):
        revision = self.owners.get(name)
        props = (await call(self.bus, owner, PATH, PROPS, "GetAll", "s", [PLAYER]))[0]
        if revision == self.owners.get(name):
            self.players[name] = dict(owner=owner, props=props, anchor=time.monotonic())

    @staticmethod
    def position(player):
        props = player["props"]
        return max(0, props.get("Position", 0) / 1e6 + (
            (time.monotonic() - player["anchor"]) * props.get("Rate", 1)
            if props.get("PlaybackStatus") == "Playing" else 0))

    def emit(self):
        rows = []
        for name, player in self.players.items():
            props = player["props"]
            md = props.get("Metadata", {})
            artist = md.get("xesam:artist", [])
            rows.append(dict(name=name, owner=player["owner"], title=md.get("xesam:title", ""),
                             artist=", ".join(artist) if isinstance(artist, list) else str(artist),
                             album=md.get("xesam:album", ""), artUrl=md.get("mpris:artUrl", ""),
                             isPlaying=props.get("PlaybackStatus") == "Playing",
                             position=self.position(player), length=md.get("mpris:length", 0) / 1e6,
                             track=md.get("mpris:trackid", ""), rate=props.get("Rate", 1)))
        self.service.publish(available=True, error="", state=rows, revision=self.revision)

    async def run(self):
        delay = 1
        while True:
            bus = None
            disconnected = None
            correction = None
            queue = asyncio.Queue()
            def handler(message):
                if message.message_type == MessageType.SIGNAL:
                    if message.interface == DBUS and message.member == "NameOwnerChanged" and message.body[0].startswith(PREFIX):
                        self.revision += 1
                        self.owners[message.body[0]] = message.body[2]
                        self.players.pop(message.body[0], None)
                    queue.put_nowait(message)
            try:
                bus = await self.service.worker.connection(BusType.SESSION)
                self.bus = bus
                bus.add_message_handler(handler)
                async def on_disconnect(watched_bus=bus, outgoing=queue):
                    try:
                        await self.service.worker.wait_disconnected(watched_bus)
                    except Exception:
                        pass
                    finally:
                        outgoing.put_nowait(None)
                disconnected = asyncio.create_task(on_disconnect())
                names = (await call(bus, DBUS, "/org/freedesktop/DBus", DBUS, "ListNames"))[0]
                self.players.clear()
                for name in names:
                    if name.startswith(PREFIX):
                        try:
                            owner = (await call(bus, DBUS, "/org/freedesktop/DBus", DBUS, "GetNameOwner", "s", [name]))[0]
                            await self.add(name, owner)
                        except Exception:
                            continue
                self.emit()
                correction = asyncio.create_task(self.correct_position())
                delay = 1
                while bus.connected:
                    message = await queue.get()
                    if message is None:
                        break
                    body = unpack(message.body)
                    if message.interface == DBUS and message.member == "NameOwnerChanged" and body[0].startswith(PREFIX):
                        name, _, owner = body
                        self.players.pop(name, None)
                        if owner:
                            try:
                                await self.add(name, owner)
                            except Exception as exc:
                                self.service.publish(error=str(exc))
                        self.emit()
                        continue
                    changed = False
                    for player in list(self.players.values()):
                        if message.sender != player["owner"] or message.path != PATH:
                            continue
                        props = player["props"]
                        if message.interface == PROPS and message.member == "PropertiesChanged" and body[0] == PLAYER:
                            props["Position"] = int(self.position(player) * 1e6)
                            player["anchor"] = time.monotonic()
                            old_track = props.get("Metadata", {}).get("mpris:trackid")
                            props.update(body[1])
                            for key in body[2]:
                                props[key] = (await call(bus, player["owner"], PATH, PROPS, "Get", "ss", [PLAYER, key]))[0]
                            if old_track != props.get("Metadata", {}).get("mpris:trackid"):
                                props["Position"] = 0
                            changed = True
                        elif message.interface == PLAYER and message.member == "Seeked":
                            props["Position"] = body[0]
                            player["anchor"] = time.monotonic()
                            changed = True
                    if changed:
                        self.emit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.service.publish(available=False, error=str(exc), state=[])
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            finally:
                for task in (disconnected, correction):
                    if task:
                        task.cancel()
                if bus:
                    bus.remove_message_handler(handler)
                self.players.clear()

    async def correct_position(self):
        while True:
            await asyncio.sleep(30)
            player = self.players.get(self.selected)
            if not player or player["props"].get("PlaybackStatus") != "Playing":
                continue
            try:
                value = (await call(self.bus, player["owner"], PATH, PROPS, "Get", "ss", [PLAYER, "Position"]))[0]
                if self.players.get(self.selected) is player:
                    player["props"]["Position"] = value
                    player["anchor"] = time.monotonic()
                    self.emit()
            except Exception as exc:
                self.service.publish(error=str(exc))

    async def command(self, name, owner, member, signature="", body=()):
        player = self.players.get(name)
        if not player or player["owner"] != owner:
            raise RuntimeError("Media player changed; please retry")
        result = await call(self.bus, owner, PATH, PLAYER, member, signature, body)
        if self.players.get(name) is not player:
            raise RuntimeError("Media player restarted; please retry")
        return result

    async def seek(self, name, owner, track, position):
        try:
            return await self.command(name, owner, "SetPosition", "ox", [track, position])
        except RuntimeError as exc:
            if "UnknownMethod" not in str(exc):
                raise
        player = self.players.get(name)
        if not player or player["owner"] != owner or player["props"].get("Metadata", {}).get("mpris:trackid") != track:
            raise RuntimeError("Track changed; please retry seeking")
        offset = position - int(self.position(player) * 1e6)
        return await self.command(name, owner, "Seek", "x", [offset])
