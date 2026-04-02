pragma Singleton

import Quickshell
import Quickshell.Io
import QtQuick
import ".."

Singleton {
    id: root

    // ── Exposed state ───────────────────────────────────────────────────
    property var    sinks:         []
    property var    sources:       []
    property var    sinkInputs:    []
    property string defaultSink:   ""
    property string defaultSource: ""

    readonly property var defaultSinkObj:   sinks.find(s => s.name === defaultSink)   ?? null
    readonly property var defaultSourceObj: sources.find(s => s.name === defaultSource) ?? null
    readonly property real masterVolume:    defaultSinkObj ? defaultSinkObj.volume  : 0
    readonly property bool masterMuted:     defaultSinkObj ? defaultSinkObj.muted   : false

    readonly property string binary: Qt.resolvedUrl("../scripts/pulse_monitor").toString().replace("file://", "")

    // Track active slider drags; while > 0 suppress monitor state writes to
    // prevent Repeater delegate destruction mid-drag.
    property int  _activeDrags:   0
    property var  _bufferedState: null

    function beginDrag() { _activeDrags++ }
    function endDrag() {
        if (_activeDrags > 0) _activeDrags--
        if (_activeDrags === 0 && _bufferedState !== null) {
            _applyState(_bufferedState)
            _bufferedState = null
        }
    }

    function _applyState(obj) {
        sinks         = obj.sinks          ?? []
        sources       = obj.sources        ?? []
        sinkInputs    = obj.sink_inputs    ?? []
        defaultSink   = obj.default_sink   ?? ""
        defaultSource = obj.default_source ?? ""
    }

    // ── Streaming monitor process ───────────────────────────────────────
    // pulse_monitor monitor streams one JSON line per state change.
    Process {
        id: monitorProc
        command: [root.binary, "monitor"]

        stdout: SplitParser {
            onRead: data => {
                try {
                    const obj = JSON.parse(data.trim())
                    if (obj.event === "state") {
                        if (root._activeDrags > 0) {
                            root._bufferedState = obj
                        } else {
                            root._applyState(obj)
                        }
                    }
                } catch (_) {}
            }
        }

        onRunningChanged: {
            if (!running) retryTimer.restart()
        }
    }

    // Retry if the monitor process exits unexpectedly
    Timer {
        id: retryTimer
        interval: 3000
        onTriggered: monitorProc.running = true
    }

    Component.onCompleted: monitorProc.running = true

    // ── Command helpers ─────────────────────────────────────────────────
    // Each mutation runs pulse_monitor as a short-lived process.

    function _run(args) {
        const proc = Qt.createQmlObject('import Quickshell.Io; Process {}', root)
        proc.command = [root.binary].concat(args)
        proc.running = true
    }

    // Single persistent process + one-slot pending queue for drag operations.
    // Prevents process pile-up when called at 60 fps without array churn.
    Process {
        id: applyProc
        property var pendingArgs: null
        command: [root.binary]
        onRunningChanged: {
            if (!running && pendingArgs !== null) {
                command = [root.binary].concat(pendingArgs)
                pendingArgs = null
                running = true
            }
        }
    }

    function _applyQueued(args) {
        if (applyProc.running) {
            applyProc.pendingArgs = args
            return
        }
        applyProc.command = [root.binary].concat(args)
        applyProc.pendingArgs = null
        applyProc.running = true
    }

    // Drag-only variants: no array churn, process-queued. Use for onDragging.
    function applySinkVolume(index, vol) {
        _applyQueued(["set-sink-volume", String(index), Math.max(0, Math.min(1, vol)).toFixed(4)])
    }
    function applySourceVolume(index, vol) {
        _applyQueued(["set-source-volume", String(index), Math.max(0, Math.min(1, vol)).toFixed(4)])
    }
    function applySinkInputVolume(index, vol) {
        _applyQueued(["set-sink-input-volume", String(index), Math.max(0, Math.min(1, vol)).toFixed(4)])
    }

    function setSinkVolume(index, vol) {
        const v = Math.max(0, Math.min(1, vol))
        // Optimistic UI update
        const i = sinks.findIndex(s => s.index === index)
        if (i >= 0) {
            const copy = sinks.slice()
            copy[i] = Object.assign({}, copy[i], { volume: v })
            sinks = copy
        }
        _run(["set-sink-volume", String(index), v.toFixed(4)])
    }

    function setSourceVolume(index, vol) {
        const v = Math.max(0, Math.min(1, vol))
        const i = sources.findIndex(s => s.index === index)
        if (i >= 0) {
            const copy = sources.slice()
            copy[i] = Object.assign({}, copy[i], { volume: v })
            sources = copy
        }
        _run(["set-source-volume", String(index), v.toFixed(4)])
    }

    function setSinkInputVolume(index, vol) {
        const v = Math.max(0, Math.min(1, vol))
        const i = sinkInputs.findIndex(s => s.index === index)
        if (i >= 0) {
            const copy = sinkInputs.slice()
            copy[i] = Object.assign({}, copy[i], { volume: v })
            sinkInputs = copy
        }
        _run(["set-sink-input-volume", String(index), v.toFixed(4)])
    }

    function setDefaultSink(name) {
        defaultSink = name
        _run(["set-default-sink", name])
    }

    function setDefaultSource(name) {
        defaultSource = name
        _run(["set-default-source", name])
    }

    function moveSinkInput(streamIndex, sinkIndex) {
        const i = sinkInputs.findIndex(s => s.index === streamIndex)
        if (i >= 0) {
            const copy = sinkInputs.slice()
            copy[i] = Object.assign({}, copy[i], { sink_index: sinkIndex })
            sinkInputs = copy
        }
        _run(["move-sink-input", String(streamIndex), String(sinkIndex)])
    }

    function toggleSinkMute(index) {
        const i = sinks.findIndex(s => s.index === index)
        if (i < 0) return
        const muted = !sinks[i].muted
        const copy = sinks.slice()
        copy[i] = Object.assign({}, copy[i], { muted: muted })
        sinks = copy
        _run(["set-sink-mute", String(index), muted ? "1" : "0"])
    }

    function toggleSourceMute(index) {
        const i = sources.findIndex(s => s.index === index)
        if (i < 0) return
        const muted = !sources[i].muted
        const copy = sources.slice()
        copy[i] = Object.assign({}, copy[i], { muted: muted })
        sources = copy
        _run(["set-source-mute", String(index), muted ? "1" : "0"])
    }

    function toggleSinkInputMute(index) {
        const i = sinkInputs.findIndex(s => s.index === index)
        if (i < 0) return
        const muted = !sinkInputs[i].muted
        const copy = sinkInputs.slice()
        copy[i] = Object.assign({}, copy[i], { muted: muted })
        sinkInputs = copy
        _run(["set-sink-input-mute", String(index), muted ? "1" : "0"])
    }
}
