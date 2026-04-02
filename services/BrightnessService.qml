pragma Singleton

import Quickshell
import Quickshell.Io
import QtQuick
import ".."

Singleton {
    // [{name: string, brightness: number 0.0–1.0}]
    property var displays: []

    readonly property string script: Qt.resolvedUrl("../scripts/brightness").toString().replace("file://", "")

    Process {
        id: listProc
        command: [BrightnessService.script, "list"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    const parsed = JSON.parse(data.trim())
                    if (Array.isArray(parsed)) BrightnessService.displays = parsed
                } catch (_) {}
            }
        }
    }

    Process {
        id: setProc
        property string display: ""
        property string value: "1.000"
        command: [BrightnessService.script, "set", setProc.display, setProc.value]
        onRunningChanged: if (!running) listProc.running = true
    }

    function setDisplay(name, value) {
        const v = Math.max(0.05, Math.min(1.0, value))
        // Optimistic local update for snappy slider feel
        const idx = displays.findIndex(d => d.name === name)
        if (idx >= 0) {
            const copy = displays.slice()
            copy[idx] = Object.assign({}, copy[idx], { brightness: v })
            displays = copy
        }
        setProc.display = name
        setProc.value   = v.toFixed(3)
        setProc.running = true
    }

    Component.onCompleted: listProc.running = true
}
