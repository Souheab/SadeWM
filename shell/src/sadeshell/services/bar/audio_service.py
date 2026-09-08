"""AudioService — non-blocking PulseAudio monitoring and control via pulsectl."""

import threading

from PySide6.QtCore import QObject, Property, QTimer, Qt, Signal, Slot

try:
    import pulsectl
    HAS_PULSECTL = True
except ImportError:
    HAS_PULSECTL = False


class AudioService(QObject):
    sinksChanged = Signal()
    sourcesChanged = Signal()
    sinkInputsChanged = Signal()
    defaultSinkChanged = Signal()
    defaultSourceChanged = Signal()
    masterVolumeChanged = Signal()
    masterMutedChanged = Signal()
    _stateReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sinks = []
        self._sources = []
        self._sink_inputs = []
        self._default_sink = ""
        self._default_source = ""
        self._active_drags = 0
        self._buffered_state = None

        self._work_ready = threading.Condition()
        self._commands = []
        self._coalesced_commands = {}
        self._poll_requested = False
        self._stopping = False
        self._worker = None
        self._poll_timer = None

        self._stateReady.connect(
            self._receive_state, Qt.ConnectionType.QueuedConnection
        )

        if HAS_PULSECTL:
            self._worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="sadeshell-audio",
            )
            self._worker.start()

            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(1000)
            self._poll_timer.timeout.connect(self._request_poll)
            self._poll_timer.start()
            self._request_poll()

    @staticmethod
    def _format_sink(s):
        vol = s.volume.value_flat if s.volume else 0.0
        return {
            "index": s.index,
            "name": s.name,
            "description": s.description or s.name,
            "volume": round(vol, 4),
            "muted": bool(s.mute),
        }

    @staticmethod
    def _format_source(s):
        vol = s.volume.value_flat if s.volume else 0.0
        return {
            "index": s.index,
            "name": s.name,
            "description": s.description or s.name,
            "volume": round(vol, 4),
            "muted": bool(s.mute),
        }

    @staticmethod
    def _format_sink_input(si):
        vol = si.volume.value_flat if si.volume else 0.0
        return {
            "index": si.index,
            "name": si.name or "Unknown",
            "volume": round(vol, 4),
            "muted": bool(si.mute),
            "sink_index": si.sink,
        }

    def _read_state(self, pulse):
        sinks = [self._format_sink(s) for s in pulse.sink_list()]
        sources = [
            self._format_source(s)
            for s in pulse.source_list()
            if ".monitor" not in (s.name or "")
        ]
        sink_inputs = [
            self._format_sink_input(si) for si in pulse.sink_input_list()
        ]
        server_info = pulse.server_info()
        return {
            "sinks": sinks,
            "sources": sources,
            "sink_inputs": sink_inputs,
            "default_sink": server_info.default_sink_name or "",
            "default_source": server_info.default_source_name or "",
        }

    @staticmethod
    def _find_by_index(items, index):
        return next(item for item in items if item.index == index)

    def _execute_command(self, pulse, command):
        operation, *args = command
        if operation == "set_sink_volume":
            index, volume = args
            pulse.volume_set_all_chans(
                self._find_by_index(pulse.sink_list(), index), volume
            )
        elif operation == "set_source_volume":
            index, volume = args
            pulse.volume_set_all_chans(
                self._find_by_index(pulse.source_list(), index), volume
            )
        elif operation == "set_sink_input_volume":
            index, volume = args
            pulse.volume_set_all_chans(
                self._find_by_index(pulse.sink_input_list(), index), volume
            )
        elif operation == "set_default_sink":
            (name,) = args
            pulse.default_set(next(s for s in pulse.sink_list() if s.name == name))
        elif operation == "set_default_source":
            (name,) = args
            pulse.default_set(next(s for s in pulse.source_list() if s.name == name))
        elif operation == "move_sink_input":
            pulse.sink_input_move(*args)
        elif operation == "set_sink_mute":
            index, muted = args
            pulse.mute(self._find_by_index(pulse.sink_list(), index), muted)
        elif operation == "set_source_mute":
            index, muted = args
            pulse.mute(self._find_by_index(pulse.source_list(), index), muted)
        elif operation == "set_sink_input_mute":
            index, muted = args
            pulse.mute(self._find_by_index(pulse.sink_input_list(), index), muted)

    def _queue_command(self, command, coalesce_key=None):
        if not HAS_PULSECTL:
            return
        with self._work_ready:
            if self._stopping:
                return
            if coalesce_key is None:
                self._commands.append(command)
            else:
                self._coalesced_commands[coalesce_key] = command
            self._work_ready.notify()

    @Slot()
    def _request_poll(self):
        if not HAS_PULSECTL:
            return
        with self._work_ready:
            if self._stopping:
                return
            self._poll_requested = True
            self._work_ready.notify()

    def _drain_pending_work(self):
        """Take one serialized batch; coalesced commands contain only latest values."""
        with self._work_ready:
            commands = self._commands
            self._commands = []
            commands.extend(self._coalesced_commands.values())
            self._coalesced_commands = {}
            poll_requested = self._poll_requested
            self._poll_requested = False
        return commands, poll_requested

    @staticmethod
    def _close_pulse(pulse):
        if pulse is not None:
            try:
                pulse.close()
            except Exception:
                pass

    def _worker_loop(self):
        """Own the sole Pulse connection and serialize all polling and commands."""
        pulse = None
        try:
            while True:
                with self._work_ready:
                    while (
                        not self._stopping
                        and not self._poll_requested
                        and not self._commands
                        and not self._coalesced_commands
                    ):
                        self._work_ready.wait()
                    if self._stopping:
                        return

                commands, poll_requested = self._drain_pending_work()
                wants_state = poll_requested or bool(commands)

                for command in commands:
                    # A disconnected Pulse server gets one fresh-connection
                    # retry without dropping later commands in the batch.
                    for _attempt in range(2):
                        try:
                            if pulse is None:
                                pulse = pulsectl.Pulse("sadeshell")
                            self._execute_command(pulse, command)
                            break
                        except Exception:
                            self._close_pulse(pulse)
                            pulse = None

                if wants_state:
                    for _attempt in range(2):
                        try:
                            if pulse is None:
                                pulse = pulsectl.Pulse("sadeshell")
                            self._stateReady.emit(self._read_state(pulse))
                            break
                        except Exception:
                            self._close_pulse(pulse)
                            pulse = None
        finally:
            self._close_pulse(pulse)

    @Slot(object)
    def _receive_state(self, state):
        # This slot is reached through a queued Qt signal, so all QObject and
        # model mutation remains on the GUI thread.
        if self._active_drags > 0:
            self._buffered_state = state
        else:
            self._apply_state(state)

    def _apply_state(self, state):
        old_master_vol = self._get_master_volume()
        old_master_muted = self._get_master_muted()

        if self._sinks != state["sinks"]:
            self._sinks = state["sinks"]
            self.sinksChanged.emit()
        if self._sources != state["sources"]:
            self._sources = state["sources"]
            self.sourcesChanged.emit()
        if self._sink_inputs != state["sink_inputs"]:
            self._sink_inputs = state["sink_inputs"]
            self.sinkInputsChanged.emit()
        if self._default_sink != state["default_sink"]:
            self._default_sink = state["default_sink"]
            self.defaultSinkChanged.emit()
        if self._default_source != state["default_source"]:
            self._default_source = state["default_source"]
            self.defaultSourceChanged.emit()

        if self._get_master_volume() != old_master_vol:
            self.masterVolumeChanged.emit()
        if self._get_master_muted() != old_master_muted:
            self.masterMutedChanged.emit()

    def _get_default_sink_obj(self):
        for sink in self._sinks:
            if sink["name"] == self._default_sink:
                return sink
        return None

    def _get_master_volume(self):
        obj = self._get_default_sink_obj()
        return obj["volume"] if obj else 0.0

    def _get_master_muted(self):
        obj = self._get_default_sink_obj()
        return obj["muted"] if obj else False

    @Property("QVariantList", notify=sinksChanged)
    def sinks(self):
        return self._sinks

    @Property("QVariantList", notify=sourcesChanged)
    def sources(self):
        return self._sources

    @Property("QVariantList", notify=sinkInputsChanged)
    def sinkInputs(self):
        return self._sink_inputs

    @Property(str, notify=defaultSinkChanged)
    def defaultSink(self):
        return self._default_sink

    @Property(str, notify=defaultSourceChanged)
    def defaultSource(self):
        return self._default_source

    @Property(float, notify=masterVolumeChanged)
    def masterVolume(self):
        return self._get_master_volume()

    @Property(bool, notify=masterMutedChanged)
    def masterMuted(self):
        return self._get_master_muted()

    @Slot()
    def beginDrag(self):
        self._active_drags += 1

    @Slot()
    def endDrag(self):
        if self._active_drags > 0:
            self._active_drags -= 1
        if self._active_drags == 0 and self._buffered_state is not None:
            self._apply_state(self._buffered_state)
            self._buffered_state = None

    @Slot(int, float)
    def setSinkVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        for i, sink in enumerate(self._sinks):
            if sink["index"] == index:
                self._sinks[i] = {**sink, "volume": round(vol, 4)}
                self.sinksChanged.emit()
                self.masterVolumeChanged.emit()
                break
        self._queue_command(
            ("set_sink_volume", index, vol), ("sink_volume", index)
        )

    @Slot(int, float)
    def applySinkVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._queue_command(
            ("set_sink_volume", index, vol), ("sink_volume", index)
        )

    @Slot(int, float)
    def setSourceVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        for i, source in enumerate(self._sources):
            if source["index"] == index:
                self._sources[i] = {**source, "volume": round(vol, 4)}
                self.sourcesChanged.emit()
                break
        self._queue_command(
            ("set_source_volume", index, vol), ("source_volume", index)
        )

    @Slot(int, float)
    def applySourceVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._queue_command(
            ("set_source_volume", index, vol), ("source_volume", index)
        )

    @Slot(int, float)
    def setSinkInputVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        for i, sink_input in enumerate(self._sink_inputs):
            if sink_input["index"] == index:
                self._sink_inputs[i] = {
                    **sink_input,
                    "volume": round(vol, 4),
                }
                self.sinkInputsChanged.emit()
                break
        self._queue_command(
            ("set_sink_input_volume", index, vol),
            ("sink_input_volume", index),
        )

    @Slot(int, float)
    def applySinkInputVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._queue_command(
            ("set_sink_input_volume", index, vol),
            ("sink_input_volume", index),
        )

    @Slot(str)
    def setDefaultSink(self, name):
        self._default_sink = name
        self.defaultSinkChanged.emit()
        self.masterVolumeChanged.emit()
        self.masterMutedChanged.emit()
        self._queue_command(("set_default_sink", name))

    @Slot(str)
    def setDefaultSource(self, name):
        self._default_source = name
        self.defaultSourceChanged.emit()
        self._queue_command(("set_default_source", name))

    @Slot(int, int)
    def moveSinkInput(self, stream_index, sink_index):
        for i, sink_input in enumerate(self._sink_inputs):
            if sink_input["index"] == stream_index:
                self._sink_inputs[i] = {
                    **sink_input,
                    "sink_index": sink_index,
                }
                self.sinkInputsChanged.emit()
                break
        self._queue_command(("move_sink_input", stream_index, sink_index))

    @Slot(int)
    def toggleSinkMute(self, index):
        for i, sink in enumerate(self._sinks):
            if sink["index"] == index:
                muted = not sink["muted"]
                self._sinks[i] = {**sink, "muted": muted}
                self.sinksChanged.emit()
                self.masterMutedChanged.emit()
                self._queue_command(("set_sink_mute", index, muted))
                return

    @Slot(int)
    def toggleSourceMute(self, index):
        for i, source in enumerate(self._sources):
            if source["index"] == index:
                muted = not source["muted"]
                self._sources[i] = {**source, "muted": muted}
                self.sourcesChanged.emit()
                self._queue_command(("set_source_mute", index, muted))
                return

    @Slot(int)
    def toggleSinkInputMute(self, index):
        for i, sink_input in enumerate(self._sink_inputs):
            if sink_input["index"] == index:
                muted = not sink_input["muted"]
                self._sink_inputs[i] = {**sink_input, "muted": muted}
                self.sinkInputsChanged.emit()
                self._queue_command(("set_sink_input_mute", index, muted))
                return

    @Slot()
    def stop(self):
        if self._poll_timer is not None:
            self._poll_timer.stop()
        with self._work_ready:
            if self._stopping:
                return
            self._stopping = True
            self._commands = []
            self._coalesced_commands = {}
            self._work_ready.notify_all()
        if self._worker is not None and self._worker is not threading.current_thread():
            self._worker.join(timeout=2.0)
