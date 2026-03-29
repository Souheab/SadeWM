pragma Singleton

import Quickshell
import Quickshell.Io
import QtQuick
import ".."

Singleton {
    property string volume: "100%"

    Process {
        id: proc
        command: ["bash", "-c", "pamixer --get-volume"]

        stdout: SplitParser {
            onRead: data => {
                var vol = data.trim()
                if (vol.length > 0) {
                    VolumeService.volume = vol + "%"
                }
            }
        }
    }

    Timer {
        interval: Theme.volumePollInterval
        running: true
        repeat: true
        onTriggered: proc.running = true
    }
}
