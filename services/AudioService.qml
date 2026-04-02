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
                        root.sinks         = obj.sinks         ?? []
                        root.sources       = obj.sources       ?? []
                        root.sinkInputs    = obj.sink_inputs   ?? []
                        root.defaultSink   = obj.default_sink  ?? ""
                        root.defaultSource = obj.default_source ?? ""
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
