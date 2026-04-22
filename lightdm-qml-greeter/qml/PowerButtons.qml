import QtQuick 2.15
import "." as Sadewm

// Row of power-action pills in the top-right corner.
// Each action is only shown if the running lightdm daemon says it is
// possible (PowerInterface.can*).
Row {
    id: root
    spacing: Sadewm.Theme.spacingSM

    PillButton {
        text: "Suspend"
        iconText: "\uf186"
        visible: power.canSuspend
        onClicked: power.suspend()
    }
    PillButton {
        text: "Hibernate"
        iconText: "\uf7c9"
        visible: power.canHibernate
        onClicked: power.hibernate()
    }
    PillButton {
        text: "Restart"
        iconText: "\uf2f1"
        visible: power.canRestart
        onClicked: power.restart()
    }
    PillButton {
        text: "Shutdown"
        iconText: "\uf011"
        danger: true
        visible: power.canShutdown
        onClicked: power.shutdown()
    }
}
