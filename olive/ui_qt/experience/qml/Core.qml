import QtQuick
import QtQuick.Shapes

Item {
    id: core
    property string phase: experience.coreState
    property bool ambient: false
    readonly property var t: tokens.values
    readonly property color tone: phase === "ERROR" ? t.error : phase === "WAITING_FOR_APPROVAL" ? t.approval : phase === "DEGRADED" || phase === "PAUSED" ? t.warning : t.accent
    readonly property bool moving: visible && experience.windowActive && !experience.reducedMotion && (ambient || phase === "THINKING" || phase === "WORKING" || phase === "RESEARCHING")
    Accessible.role: Accessible.Indicator
    Accessible.name: "OLIVE Core: " + phase.replace(/_/g, " ").toLowerCase()
    Rectangle {
        width: parent.width * 0.56; height: width; radius: width / 2
        anchors.centerIn: parent
        color: core.tone; opacity: 0.025
    }
    Rectangle {
        width: parent.width * 0.28; height: width; radius: width / 2
        anchors.centerIn: parent
        color: core.tone; opacity: 0.055
    }
    Item {
        id: rings
        anchors.fill: parent
        NumberAnimation on rotation { from: 0; to: 360; duration: core.ambient ? 36000 : 12000; loops: Animation.Infinite; running: core.moving }
        Shape {
            anchors.fill: parent
            antialiasing: true
            ShapePath {
                strokeColor: core.tone; strokeWidth: Math.max(1.5, core.width * 0.006)
                fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: core.width * 0.5; centerY: core.height * 0.5; radiusX: core.width * 0.36; radiusY: core.height * 0.36; startAngle: -72; sweepAngle: 212 }
            }
            ShapePath {
                strokeColor: Qt.alpha(core.tone, 0.45); strokeWidth: Math.max(1.1, core.width * 0.0035)
                fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: core.width * 0.51; centerY: core.height * 0.49; radiusX: core.width * 0.435; radiusY: core.height * 0.435; startAngle: 106; sweepAngle: 172 }
            }
            ShapePath {
                strokeColor: Qt.alpha(core.tone, 0.22); strokeWidth: Math.max(1, core.width * 0.003)
                fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: core.width * 0.5; centerY: core.height * 0.5; radiusX: core.width * 0.28; radiusY: core.height * 0.28; startAngle: 170; sweepAngle: 245 }
            }
        }
    }
    Rectangle {
        anchors.centerIn: parent
        width: Math.max(4, parent.width * 0.04); height: width; radius: width / 2
        color: core.tone
        Rectangle { anchors.centerIn: parent; width: parent.width * 0.44; height: width; radius: width / 2; color: core.t.text }
    }
}
