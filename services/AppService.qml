pragma Singleton

import Quickshell
import QtQuick

Singleton {
    readonly property var apps: DesktopEntries.applications.values

    function search(query) {
        const q = query.trim().toLowerCase();
        if (q === "") return apps;
        return apps.filter(entry => {
            return (entry.name        && entry.name.toLowerCase().includes(q))
                || (entry.genericName && entry.genericName.toLowerCase().includes(q))
                || (entry.comment     && entry.comment.toLowerCase().includes(q))
                || (entry.keywords    && entry.keywords.toLowerCase().includes(q));
        });
    }

    function launch(entry) {
        Quickshell.execDetached({ command: entry.command });
    }
}
