import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool quiet: false
    readonly property var t: tokens.values
    implicitHeight: t.controlHeight
    implicitWidth: Math.max(44, label.implicitWidth + 32)
    hoverEnabled: true
    font.family: t.fontFamily
    font.pixelSize: t.bodySize
    activeFocusOnTab: true
    Accessible.name: text
    opacity: enabled ? 1 : 0.45
    contentItem: Text {
        id: label
        text: control.text
        font: control.font
        color: control.primary ? control.t.onAccent : control.t.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: control.t.radius
        color: control.primary ? control.t.accent : control.down ? control.t.border : control.hovered ? control.t.elevated : control.quiet ? "transparent" : control.t.surface
        border.width: control.activeFocus ? 2 : control.quiet ? 0 : 1
        border.color: control.activeFocus ? control.t.accent : control.t.border
        Behavior on color { ColorAnimation { duration: experience.reducedMotion ? 0 : control.t.hoverMs } }
    }
    scale: down && !experience.reducedMotion ? 0.98 : 1
    Behavior on scale { NumberAnimation { duration: experience.reducedMotion ? 0 : control.t.pressMs } }
}
