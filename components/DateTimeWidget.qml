import QtQuick
import QtQuick.Layouts
import Quickshell
import ".."
import "../services"

Rectangle {
    id: dateTimeWidget
    width: Math.ceil(pillLayout.implicitWidth)
    height: Theme.containerHeight
    radius: Theme.containerRadius
    color: Theme.containerBg

    Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutQuart } }

    property bool dateOpen: false
    property bool mediaOpen: false
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
        popupX = pos.x - Theme.calendarWidth / 2;
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

    // Media Popup handling
    onMediaOpenChanged: {
        if (popupLayer) popupLayer.mediaVisible = mediaOpen;
    }

    Connections {
        target: dateTimeWidget.popupLayer
        function onPopupVisibleChanged() {
            if (dateTimeWidget.popupLayer && !dateTimeWidget.popupLayer.popupVisible) {
                dateTimeWidget.dateOpen = false;
            }
        }
        function onMediaVisibleChanged() {
            if (dateTimeWidget.popupLayer && !dateTimeWidget.popupLayer.mediaVisible) {
                dateTimeWidget.mediaOpen = false;
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

    RowLayout {
        id: pillLayout
        anchors.fill: parent
        spacing: 0

        // Time Section
        Rectangle {
            Layout.fillWidth: !MediaService.hasMedia
            Layout.preferredWidth: timeText.implicitWidth + Theme.containerPadding * (MediaService.hasMedia ? 1 : 2)
            Layout.fillHeight: true
            radius: parent.height / 2
            color: dateArea.containsMouse ? Theme.menuHover : "transparent"

            // Clip corners for the non-outer edges when media is active
            Rectangle {
                anchors.right: parent.right
                width: parent.radius
                height: parent.height
                color: parent.color
                visible: MediaService.hasMedia && parent.color !== "transparent"
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

                Text {
                    id: timeText
                    anchors.centerIn: parent
                    text: dateTimeWidget.timeStr
                    color: Theme.textColor
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.textFontSize
                }
            }
        }

        // Separator
        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            Layout.topMargin: 4
            Layout.bottomMargin: 4
            color: Theme.textColor
            opacity: 0.2
            visible: MediaService.hasMedia
        }

        // Now Playing Section
        Rectangle {
            Layout.preferredHeight: parent.height
            Layout.preferredWidth: Math.min(mediaLabel.implicitWidth + Theme.spacingSM + Theme.containerPadding, 300)
            Layout.fillHeight: true
            radius: parent.height / 2
            color: mediaArea.containsMouse ? Theme.menuHover : "transparent"
            visible: MediaService.hasMedia

            // Square the left corners to meet the separator nicely
            Rectangle {
                anchors.left: parent.left
                width: parent.radius
                height: parent.height
                color: parent.color
                visible: parent.color !== "transparent"
            }

            MouseArea {
                id: mediaArea
                anchors.fill: parent
                hoverEnabled: true

                onClicked: {
                    if (dateTimeWidget.mediaOpen) {
                        dateTimeWidget.mediaOpen = false;
                    } else {
                        dateTimeWidget.mediaOpen = true;
                    }
                }

                Row {
                    anchors.centerIn: parent
                    spacing: Theme.spacingXS
                    
                    Text {
                        id: iconText
                        text: "\uf001" // Music icon
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: 12
                        opacity: 0.7
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        id: mediaLabel
                        text: MediaService.title
                        color: Theme.textColor
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
                        elide: Text.ElideRight
                        width: Math.min(implicitWidth, Theme.mediaLabelMaxWidth)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
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
        visible: opacity > 0
        opacity: dateTimeWidget.dateOpen ? 1.0 : 0.0
        x: dateTimeWidget.popupX
        y: dateTimeWidget.popupY
        width: Theme.calendarWidth
        height: calendarContent.height + 20
        color: Theme.menuBg
        radius: Theme.menuRadius
        border.color: Theme.menuBorder
        border.width: 1

        property real slideOffset: dateTimeWidget.dateOpen ? 0 : -12
        transform: Translate { y: datePopup.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }
        Behavior on opacity { NumberAnimation { duration: Theme.popupAnimDuration; easing.type: Theme.popupAnimEasing } }

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
                    width: Theme.containerHeight
                    height: Theme.containerHeight
                    radius: Theme.containerRadius
                    color: prevArea.containsMouse ? Theme.menuHover : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "\uf053"
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.textFontSize
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
                    width: parent.width - Theme.containerHeight * 2
                    height: Theme.containerHeight

                    Text {
                        anchors.centerIn: parent
                        text: dateTimeWidget.monthNames[dateTimeWidget.viewMonth] + " " + dateTimeWidget.viewYear
                        color: Theme.textColor
                        font.family: Theme.clockFont
                        font.pixelSize: Theme.textFontSize
                        font.bold: true
                    }
                }

                Rectangle {
                    width: Theme.containerHeight
                    height: Theme.containerHeight
                    radius: Theme.containerRadius
                    color: nextArea.containsMouse ? Theme.menuHover : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "\uf054"
                        color: Theme.textColor
                        font.family: Theme.iconFont
                        font.pixelSize: Theme.textFontSize
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
                        width: Math.floor((Theme.calendarWidth - 20) / 7)
                        horizontalAlignment: Text.AlignHCenter
                        text: modelData
                        color: Theme.dotEmpty
                        font.family: Theme.monoFont
                        font.pixelSize: Theme.textFontSize
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

                        width: Math.floor((Theme.calendarWidth - 20) / 7)
                        height: 34
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
                            font.family: Theme.monoFont
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
