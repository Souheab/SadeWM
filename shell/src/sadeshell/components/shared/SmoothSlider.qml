import QtQuick

Item {
    id: sliderRoot

    property real  value:       0
    property real  min:         0
    property color trackBg:     Theme.mediaProgressTrackBg
    property color fillColor:   Theme.mediaProgressColor
    property color thumbColor:  Theme.buttonBg
    property int   thumbSize:   12
    property int   trackHeight: 4

    readonly property real displayValue: _isDragging ? _dragValue : value
    readonly property bool isDragging:   _isDragging

    signal dragging(real v)
    signal released(real v)

    property real _dragValue: value
    property bool _isDragging: false

    onValueChanged: if (!_isDragging) _dragValue = value

    implicitWidth:  100
    implicitHeight: thumbSize

    Timer {
        interval: 16
        repeat:   true
        running:  sliderRoot._isDragging
        onTriggered: sliderRoot.dragging(sliderRoot._dragValue)
    }

    Rectangle {
        id: track
        anchors.left:            parent.left
        anchors.right:           parent.right
        anchors.verticalCenter:  parent.verticalCenter
        height: sliderRoot.trackHeight
        radius: sliderRoot.trackHeight / 2
        color:  sliderRoot.trackBg

        Rectangle {
            width:  parent.width * sliderRoot.displayValue
            height: parent.height
            radius: parent.radius
            color:  sliderRoot.fillColor
        }

        Rectangle {
            width:  sliderRoot.thumbSize
            height: sliderRoot.thumbSize
            radius: sliderRoot.thumbSize / 2
            color:  sliderRoot.thumbColor
            border.color: Theme.textColor
            border.width: 1
            anchors.verticalCenter: parent.verticalCenter
            x: Math.max(0, Math.min(track.width - width,
                   sliderRoot.displayValue * track.width - width / 2))
        }
    }

    MouseArea {
        anchors.fill:    parent
        preventStealing: true
        cursorShape:     Qt.PointingHandCursor

        function _ratio(mx) {
            return Math.max(sliderRoot.min, Math.min(1.0, mx / track.width))
        }

        onPressed:         mouse => { sliderRoot._dragValue  = _ratio(mouse.x)
                                      sliderRoot._isDragging = true }
        onPositionChanged: mouse => { if (pressed) sliderRoot._dragValue = _ratio(mouse.x) }
        onReleased:        mouse => { sliderRoot._isDragging = false
                                      sliderRoot.released(sliderRoot._dragValue) }
    }
}
