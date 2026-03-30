pragma Singleton

import Quickshell
import Quickshell.Io
import QtQuick
import ".."

Singleton {
    property bool wifiEnabled: false
    property string connectedSsid: ""
    property int connectedSignal: 0
    property var networks: []
    property bool scanning: false

    readonly property string qsctrl: Qt.resolvedUrl("../scripts/qsctrl").toString().replace("file://", "")

    // ── Status polling ─────────────────────────────────────────────────────
    Process {
        id: statusProc
        command: ["python3", WiFiService.qsctrl, "wifi", "status"]

        stdout: SplitParser {
            onRead: data => {
                try {
                    const obj = JSON.parse(data.trim());
                    WiFiService.wifiEnabled     = obj.enabled  ?? false;
                    WiFiService.connectedSsid   = obj.ssid     ?? "";
                    WiFiService.connectedSignal = obj.signal   ?? 0;
                } catch (_) {}
            }
        }
    }

    Timer {
        interval: 10000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: statusProc.running = true
    }

    // ── Network list ───────────────────────────────────────────────────────
    Process {
        id: listProc
        command: ["python3", WiFiService.qsctrl, "wifi", "list"]

        onRunningChanged: if (!running) WiFiService.scanning = false

        stdout: SplitParser {
            onRead: data => {
                try {
                    WiFiService.networks = JSON.parse(data.trim());
                } catch (_) {}
            }
        }
    }

    Process {
        id: scanProc
        command: ["python3", WiFiService.qsctrl, "wifi", "scan"]

        onRunningChanged: {
            if (!running) {
                WiFiService.scanning = false;
                statusProc.running = true;
            }
        }

        stdout: SplitParser {
            onRead: data => {
                try {
                    WiFiService.networks = JSON.parse(data.trim());
                } catch (_) {}
            }
        }
    }

    // ── Control processes ──────────────────────────────────────────────────
    Process {
        id: toggleProc
        onRunningChanged: if (!running) statusProc.running = true
    }

    Process {
        id: connectProc
        onRunningChanged: if (!running) statusProc.running = true
    }

    // ── Public API ─────────────────────────────────────────────────────────
    function scan() {
        if (scanning) return;
        scanning = true;
        scanProc.running = true;
    }

    function refreshList() {
        listProc.running = true;
    }

    function toggleWifi() {
        toggleProc.command = ["python3", qsctrl, "wifi", "toggle"];
        toggleProc.running = true;
    }

    function connectTo(ssid) {
        connectProc.command = ["python3", qsctrl, "wifi", "connect", ssid];
        connectProc.running = true;
    }
}
