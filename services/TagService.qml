pragma Singleton

import Quickshell
import Quickshell.Io

Singleton {
    property var tags: []

    Process {
        id: proc
        running: true
        command: [Qt.resolvedUrl("../scripts/qsctrl"), "tags", "watch"]

        stdout: SplitParser {
            onRead: data => {
                try {
                    const json = JSON.parse(data);
                    if (json.ok && Array.isArray(json.tags_state)) {
                        TagService.tags = json.tags_state;
                    }
                } catch (e) {
                    console.error("Failed to parse tags_state JSON:", e);
                }
            }
        }
    }
}
