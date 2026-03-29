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
        command: ["bash", "-c", "echo 'local sel,occ,urg=\"\",\"\",\"\"; for _,t in ipairs(require(\"awful\").screen.focused().tags) do if t.selected then sel=sel..t.name end; if #t:clients()>0 then occ=occ..t.name end; if t.urgent then urg=urg..t.name end end; return sel..\"|\"..occ..\"|\"..urg' | awesome-client"]

        stdout: SplitParser {
            onRead: data => {
                var match = data.match(/string "([^"]*)"/);
                if (match && match[1]) {
                    var parts = match[1].split("|");
                    TagService.selected = parts[0].split("").map(function(t) { return parseInt(t) });
                    TagService.occupied = parts[1] ? parts[1].split("").map(function(t) { return parseInt(t) }) : [];
                    TagService.urgent = parts[2] ? parts[2].split("").map(function(t) { return parseInt(t) }) : [];
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
