"""AudioService — PulseAudio monitoring and control via pulsectl."""

import json
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sinks = []
        self._sources = []
        self._sink_inputs = []
        self._default_sink = ""
        self._default_source = ""
        self._active_drags = 0
        self._buffered_state = None

        if HAS_PULSECTL:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(1000)
            self._poll_timer.timeout.connect(self._poll)
            self._poll_timer.start()
            self._poll()

    def _format_sink(self, s):
        vol = s.volume.value_flat if s.volume else 0.0
        return {
            "index": s.index,
            "name": s.name,
            "description": s.description or s.name,
            "volume": round(vol, 4),
            "muted": bool(s.mute),
        }

    def _format_source(self, s):
        vol = s.volume.value_flat if s.volume else 0.0
        return {
            "index": s.index,
            "name": s.name,
            "description": s.description or s.name,
            "volume": round(vol, 4),
            "muted": bool(s.mute),
        }

    def _format_sink_input(self, si):
        vol = si.volume.value_flat if si.volume else 0.0
        return {
            "index": si.index,
            "name": si.name or "Unknown",
            "volume": round(vol, 4),
            "muted": bool(si.mute),
            "sink_index": si.sink,
        }

    def _poll(self):
        if not HAS_PULSECTL:
            return
        try:
            with pulsectl.Pulse("sadeshell-poll") as pulse:
                sinks = [self._format_sink(s) for s in pulse.sink_list()]
                sources = [self._format_source(s) for s in pulse.source_list()
                           if ".monitor" not in (s.name or "")]
                sink_inputs = [self._format_sink_input(si) for si in pulse.sink_input_list()]
                server_info = pulse.server_info()
                default_sink = server_info.default_sink_name or ""
                default_source = server_info.default_source_name or ""

            state = {
                "sinks": sinks,
                "sources": sources,
                "sink_inputs": sink_inputs,
                "default_sink": default_sink,
                "default_source": default_source,
            }

            if self._active_drags > 0:
                self._buffered_state = state
            else:
                self._apply_state(state)
        except Exception:
            pass

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
        for s in self._sinks:
            if s["name"] == self._default_sink:
                return s
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

    def _pulse_cmd(self, func):
        """Run a pulsectl command in a thread to avoid blocking the UI."""
        def _run():
            try:
                with pulsectl.Pulse("sadeshell-cmd") as pulse:
                    func(pulse)
            except Exception:
                pass
            self._poll()
        threading.Thread(target=_run, daemon=True).start()

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
        # Optimistic update
        for i, s in enumerate(self._sinks):
            if s["index"] == index:
                self._sinks[i] = {**s, "volume": round(vol, 4)}
                self.sinksChanged.emit()
                self.masterVolumeChanged.emit()
                break
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            p.sink_list()[next(j for j, s in enumerate(p.sink_list()) if s.index == index)], vol))

    @Slot(int, float)
    def applySinkVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            next(s for s in p.sink_list() if s.index == index), vol))

    @Slot(int, float)
    def setSourceVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        for i, s in enumerate(self._sources):
            if s["index"] == index:
                self._sources[i] = {**s, "volume": round(vol, 4)}
                self.sourcesChanged.emit()
                break
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            next(s for s in p.source_list() if s.index == index), vol))

    @Slot(int, float)
    def applySourceVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            next(s for s in p.source_list() if s.index == index), vol))

    @Slot(int, float)
    def setSinkInputVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        for i, si in enumerate(self._sink_inputs):
            if si["index"] == index:
                self._sink_inputs[i] = {**si, "volume": round(vol, 4)}
                self.sinkInputsChanged.emit()
                break
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            next(si for si in p.sink_input_list() if si.index == index), vol))

    @Slot(int, float)
    def applySinkInputVolume(self, index, vol):
        vol = max(0.0, min(1.0, vol))
        self._pulse_cmd(lambda p: p.volume_set_all_chans(
            next(si for si in p.sink_input_list() if si.index == index), vol))

    @Slot(str)
    def setDefaultSink(self, name):
        self._default_sink = name
        self.defaultSinkChanged.emit()
        self.masterVolumeChanged.emit()
        self.masterMutedChanged.emit()
        self._pulse_cmd(lambda p: p.default_set(next(s for s in p.sink_list() if s.name == name)))

    @Slot(str)
    def setDefaultSource(self, name):
        self._default_source = name
        self.defaultSourceChanged.emit()
        self._pulse_cmd(lambda p: p.default_set(next(s for s in p.source_list() if s.name == name)))

    @Slot(int, int)
    def moveSinkInput(self, stream_index, sink_index):
        for i, si in enumerate(self._sink_inputs):
            if si["index"] == stream_index:
                self._sink_inputs[i] = {**si, "sink_index": sink_index}
                self.sinkInputsChanged.emit()
                break
        self._pulse_cmd(lambda p: p.sink_input_move(stream_index, sink_index))

    @Slot(int)
    def toggleSinkMute(self, index):
        for i, s in enumerate(self._sinks):
            if s["index"] == index:
                muted = not s["muted"]
                self._sinks[i] = {**s, "muted": muted}
                self.sinksChanged.emit()
                self.masterMutedChanged.emit()
                self._pulse_cmd(lambda p: p.mute(
                    next(sk for sk in p.sink_list() if sk.index == index), muted))
                return

    @Slot(int)
    def toggleSourceMute(self, index):
        for i, s in enumerate(self._sources):
            if s["index"] == index:
                muted = not s["muted"]
                self._sources[i] = {**s, "muted": muted}
                self.sourcesChanged.emit()
                self._pulse_cmd(lambda p: p.mute(
                    next(sk for sk in p.source_list() if sk.index == index), muted))
                return

    @Slot(int)
    def toggleSinkInputMute(self, index):
        for i, si in enumerate(self._sink_inputs):
            if si["index"] == index:
                muted = not si["muted"]
                self._sink_inputs[i] = {**si, "muted": muted}
                self.sinkInputsChanged.emit()
                self._pulse_cmd(lambda p: p.mute(
                    next(s for s in p.sink_input_list() if s.index == index), muted))
                return
