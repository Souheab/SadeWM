// Smooth draggable slider that decouples visual state from external data.
// The visual position updates instantly on every mouse move; callbacks to
// the service are throttled to ~60 fps via the repeat Timer so process
// queues never pile up.
//
// Usage:
//   SmoothSlider {
//       value: someService.level        // normalized 0-1 from outside
//       min:   0.05                     // optional floor (default 0)
//       onDragging: v => service.applyXxx(v)  // throttled, opt-in
//       onReleased: v => service.setXxx(v)    // once on mouse-up
//   }
//
// External labels should read `slider.displayValue`, not `slider.value`.

import QtQuick
import ".."

Item {
    id: sliderRoot

    // ── Public API ────────────────────────────────────────────────────────
    property real  value:       0
    property real  min:         0
    property color trackBg:     Theme.mediaProgressTrackBg
    property color fillColor:   Theme.mediaProgressColor
    property color thumbColor:  Theme.buttonBg
    property int   thumbSize:   12
    property int   trackHeight: 4

    // What labels should display (local during drag, external otherwise)
    readonly property real displayValue: _isDragging ? _dragValue : value
    readonly property bool isDragging:   _isDragging

    // Fired at ~60 fps while dragging — connect to a lightweight apply function
    signal dragging(real v)
    // Fired once on mouse release — connect to the committing setter
    signal released(real v)

    // ── Internals ─────────────────────────────────────────────────────────
    property real _dragValue: value
    property bool _isDragging: false

    // Keep shadow in sync with service when idle
    onValueChanged: if (!_isDragging) _dragValue = value

    implicitWidth:  100
    implicitHeight: thumbSize

    Timer {
        interval: 16
        repeat:   true
        running:  sliderRoot._isDragging
        onTriggered: sliderRoot.dragging(sliderRoot._dragValue)
    }

    // ── Track ─────────────────────────────────────────────────────────────
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

    // ── Interaction ───────────────────────────────────────────────────────
    // The MouseArea covers the full item height so slight vertical drift
    // during a drag never breaks the grab. QML keeps the grab active outside
    // the item bounds once pressed, so the user can drag freely.
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
