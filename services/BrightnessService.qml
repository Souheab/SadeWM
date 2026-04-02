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
        // Queue at most one pending call so xrandr processes never pile up
        property string pendingDisplay: ""
        property string pendingValue: ""
        command: [BrightnessService.script, "set", setProc.display, setProc.value]
        onRunningChanged: {
            if (!running && pendingValue !== "") {
                display = pendingDisplay
                value = pendingValue
                pendingDisplay = ""
                pendingValue = ""
                running = true
            }
        }
    }

    // Only fires xrandr — does NOT touch displays[]. Safe to call at 60fps during drag.
    function applyBrightness(name, value) {
        const v = Math.max(0.05, Math.min(1.0, value)).toFixed(3)
        if (setProc.running) {
            setProc.pendingDisplay = name
            setProc.pendingValue = v
            return
        }
        setProc.display = name
        setProc.value = v
        setProc.pendingDisplay = ""
        setProc.pendingValue = ""
        setProc.running = true
    }

    // Optimistic state update + xrandr. Use on release/click, not during drag.
    function setDisplay(name, value) {
        const v = Math.max(0.05, Math.min(1.0, value))
        const idx = displays.findIndex(d => d.name === name)
        if (idx >= 0) {
            const copy = displays.slice()
            copy[idx] = Object.assign({}, copy[idx], { brightness: v })
            displays = copy
        }
        applyBrightness(name, v)
    }

    Component.onCompleted: listProc.running = true
}
