pragma Singleton

import Quickshell
import Quickshell.Io
import QtQuick
import ".."

Singleton {
    property var selected: []
    property var occupied: []
    property var urgent: []

    Process {
        id: proc
        command: ["python3", Qt.resolvedUrl("../scripts/qsctrl").toString().replace("file://", ""), "tags", "get"]

        stdout: SplitParser {
            onRead: data => {
                const parts = data.trim().split("|");
                if (parts.length === 3) {
                    const selMask = parseInt(parts[0]) || 0;
                    const occMask = parseInt(parts[1]) || 0;
                    const urgMask = parseInt(parts[2]) || 0;

                    const sel = [];
                    const occ = [];
                    const urg = [];

                    for (let i = 0; i < Theme.tagCount; i++) {
                        const mask = 1 << i;
                        if (selMask & mask) sel.push(i + 1);
                        if (occMask & mask) occ.push(i + 1);
                        if (urgMask & mask) urg.push(i + 1);
                    }

                    TagService.selected = sel;
                    TagService.occupied = occ;
                    TagService.urgent = urg;
                }
            }
        }
    }

    Timer {
        interval: Theme.tagPollInterval
        running: true
        repeat: true
        onTriggered: proc.running = true
    }
}
