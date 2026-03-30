import QtQuick
import Quickshell
import ".."

Rectangle {
    id: dateTimeWidget
    width: timeText.width + Theme.containerPadding
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: dateArea.containsMouse ? Theme.menuHover : Theme.containerBg

    property bool dateOpen: false
    property string timeStr: ""
    property string dateStr: ""

    property real popupX: 0
    property real popupY: 0

    readonly property Item popupLayer: {
        let p = parent;
        while (p) {
            for (let i = 0; i < p.children.length; i++) {
                if (p.children[i].objectName === "popupLayer")
                    return p.children[i];
            }
            p = p.parent;
        }
        return null;
    }

    function updatePopupPosition() {
        if (!popupLayer) return;
        const pos = dateTimeWidget.mapToItem(popupLayer, dateTimeWidget.width / 2, dateTimeWidget.height);
        popupX = pos.x - 140; // half of 280 calendar width
        popupY = pos.y + 4;
    }

    onDateOpenChanged: {
        if (popupLayer) popupLayer.popupVisible = dateOpen;
        if (dateOpen) {
            const now = new Date();
            viewMonth = now.getMonth();
            viewYear = now.getFullYear();
        }
    }

    Connections {
        target: dateTimeWidget.popupLayer
        function onPopupVisibleChanged() {
            if (dateTimeWidget.popupLayer && !dateTimeWidget.popupLayer.popupVisible) {
                dateTimeWidget.dateOpen = false;
            }
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            const now = new Date();
            dateTimeWidget.timeStr = Qt.formatDateTime(now, Theme.timeFormat);
            dateTimeWidget.dateStr = Qt.formatDateTime(now, Theme.dateFormat);
        }
    }

    Text {
        id: timeText
        anchors.centerIn: parent
        text: dateTimeWidget.timeStr
        color: Theme.textColor
        font.pixelSize: Theme.textFontSize
        font.family: Theme.clockFont
    }

    MouseArea {
        id: dateArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
            if (dateTimeWidget.dateOpen) {
                dateTimeWidget.dateOpen = false;
            } else {
                dateTimeWidget.updatePopupPosition();
                dateTimeWidget.dateOpen = true;
            }
        }
    }

    // Calendar state
    property int viewMonth: new Date().getMonth()
    property int viewYear: new Date().getFullYear()

    function daysInMonth(month, year) {
        return new Date(year, month + 1, 0).getDate();
    }

    function firstDayOfWeek(month, year) {
        return new Date(year, month, 1).getDay();
    }

    function buildCalendarGrid() {
        const days = daysInMonth(viewMonth, viewYear);
        const startDay = firstDayOfWeek(viewMonth, viewYear);
        let cells = [];
        // Previous month trailing days
        const prevDays = daysInMonth((viewMonth + 11) % 12, viewMonth === 0 ? viewYear - 1 : viewYear);
        for (let i = startDay - 1; i >= 0; i--)
            cells.push({ day: prevDays - i, current: false });
        // Current month days
        for (let d = 1; d <= days; d++)
            cells.push({ day: d, current: true });
        // Next month leading days to fill 6 rows
        const remaining = 42 - cells.length;
        for (let n = 1; n <= remaining; n++)
            cells.push({ day: n, current: false });
        return cells;
    }

    property var calendarCells: buildCalendarGrid()
    onViewMonthChanged: calendarCells = buildCalendarGrid()
    onViewYearChanged: calendarCells = buildCalendarGrid()

    readonly property var monthNames: [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    Rectangle {
        id: datePopup
        parent: dateTimeWidget.popupLayer
        visible: dateTimeWidget.dateOpen
        x: dateTimeWidget.popupX
        y: dateTimeWidget.popupY
        width: 280
        height: calendarContent.height + 20
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        Column {
            id: calendarContent
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 10
            spacing: 8

            // Date string header
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: dateTimeWidget.dateStr
                color: Theme.textColor
                font.pixelSize: Theme.textFontSize
                font.family: Theme.clockFont
            }

            // Month/Year navigation
            Row {
                anchors.left: parent.left
                anchors.right: parent.right

                Rectangle {
                    width: 28
                    height: 28
                    radius: Theme.containerRadius
                    color: prevArea.containsMouse ? Theme.menuHover : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "◀"
                        color: Theme.textColor
                        font.pixelSize: 12
                    }
                    MouseArea {
                        id: prevArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (dateTimeWidget.viewMonth === 0) {
                                dateTimeWidget.viewMonth = 11;
                                dateTimeWidget.viewYear--;
                            } else {
                                dateTimeWidget.viewMonth--;
                            }
                        }
                    }
                }

                Item {
                    width: parent.width - 56
                    height: 28

                    Text {
                        anchors.centerIn: parent
                        text: dateTimeWidget.monthNames[dateTimeWidget.viewMonth] + " " + dateTimeWidget.viewYear
                        color: Theme.textColor
                        font.pixelSize: 13
                        font.family: Theme.clockFont
                        font.bold: true
                    }
                }

                Rectangle {
                    width: 28
                    height: 28
                    radius: Theme.containerRadius
                    color: nextArea.containsMouse ? Theme.menuHover : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "▶"
                        color: Theme.textColor
                        font.pixelSize: 12
                    }
                    MouseArea {
                        id: nextArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (dateTimeWidget.viewMonth === 11) {
                                dateTimeWidget.viewMonth = 0;
                                dateTimeWidget.viewYear++;
                            } else {
                                dateTimeWidget.viewMonth++;
                            }
                        }
                    }
                }
            }

            // Day-of-week headers
            Row {
                spacing: 0
                Repeater {
                    model: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
                    Text {
                        width: 36
                        horizontalAlignment: Text.AlignHCenter
                        text: modelData
                        color: Theme.dotEmpty
                        font.pixelSize: 11
                        font.family: Theme.clockFont
                        font.bold: true
                    }
                }
            }

            // Calendar grid (6 rows x 7 cols)
            Grid {
                columns: 7
                spacing: 0

                Repeater {
                    model: dateTimeWidget.calendarCells

                    Rectangle {
                        required property var modelData
                        required property int index

                        width: 36
                        height: 32
                        radius: Theme.containerRadius
                        color: {
                            const now = new Date();
                            if (modelData.current
                                && modelData.day === now.getDate()
                                && dateTimeWidget.viewMonth === now.getMonth()
                                && dateTimeWidget.viewYear === now.getFullYear())
                                return Theme.dotSelected;
                            return "transparent";
                        }

                        Text {
                            anchors.centerIn: parent
                            text: modelData.day
                            color: modelData.current ? Theme.textColor : Theme.dotEmpty
                            font.pixelSize: 12
                            font.family: Theme.clockFont
                        }
                    }
                }
            }
        }
    }
}
