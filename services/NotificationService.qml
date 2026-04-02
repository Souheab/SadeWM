pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Services.Notifications

Singleton {
    id: root

    // All received notifications, newest first
    property list<var> notifications: []

    // Queue of notifications to show as popups (index into notifications)
    // Each entry is the notification object itself
    property list<var> popupQueue: []

    readonly property int unreadCount: notifications.length

    function dismiss(index) {
        const n = notifications[index]
        if (n && n.notification)
            n.notification.dismiss()
        const updated = [...notifications]
        updated.splice(index, 1)
        notifications = updated
    }

    function dismissAll() {
        for (const n of notifications) {
            if (n && n.notification)
                n.notification.dismiss()
        }
        notifications = []
    }

    function removeFromQueue(entry) {
        const idx = popupQueue.indexOf(entry)
        if (idx !== -1) {
            const updated = [...popupQueue]
            updated.splice(idx, 1)
            popupQueue = updated
        }
    }

    NotificationServer {
        keepOnReload: false
        actionsSupported: true
        bodyMarkupSupported: true
        imageSupported: true
        persistenceSupported: true

        onNotification: notif => {
            notif.tracked = true
            const entry = {
                id: notif.id,
                summary: notif.summary || "",
                body: notif.body || "",
                appName: notif.appName || "",
                appIcon: notif.appIcon || "",
                image: notif.image || "",
                urgency: notif.urgency,
                expireTimeout: notif.expireTimeout > 0 ? notif.expireTimeout : 5000,
                notification: notif,
                time: new Date()
            }
            root.notifications = [entry, ...root.notifications]
            root.popupQueue = [entry, ...root.popupQueue]
        }
    }
}
