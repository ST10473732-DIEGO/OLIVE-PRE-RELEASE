import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: welcome
    readonly property var t: tokens.values
    signal enterRequested()
    Keys.onReturnPressed: if (experience.entryAllowed) enterRequested()
    Keys.onEnterPressed: if (experience.entryAllowed) enterRequested()
    Rectangle { anchors.fill: parent; color: welcome.t.background }
    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -12
        spacing: 0
        width: Math.min(parent.width - 64, 560)
        Core {
            width: Math.min(280, welcome.height * 0.36); height: width
            anchors.horizontalCenter: parent.horizontalCenter; ambient: true
            scale: experience.welcome ? 1 : 0.88
            Behavior on scale { NumberAnimation { duration: experience.reducedMotion ? 0 : welcome.t.enterMs } }
        }
        Text { text: "OLIVE"; width: parent.width; horizontalAlignment: Text.AlignHCenter; color: welcome.t.text; font.family: welcome.t.fontFamily; font.pixelSize: welcome.t.displaySize; font.weight: Font.DemiBold; font.letterSpacing: 9 }
        Item { height: 14; width: 1 }
        Text { text: "Personal Intelligence System"; width: parent.width; horizontalAlignment: Text.AlignHCenter; color: welcome.t.secondary; font.family: welcome.t.fontFamily; font.pixelSize: 18; font.letterSpacing: 0.5 }
        Item { height: 44; width: 1 }
        ActionButton { objectName: "enterOlive"; text: "Enter OLIVE"; primary: true; width: 192; anchors.horizontalCenter: parent.horizontalCenter; enabled: experience.entryAllowed; onClicked: welcome.enterRequested() }
        Item { height: 22; width: 1 }
        Text { text: experience.readiness; width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: welcome.t.muted; font.family: welcome.t.fontFamily; font.pixelSize: welcome.t.smallSize }
    }
    Text { anchors.bottom: parent.bottom; anchors.bottomMargin: 28; anchors.horizontalCenter: parent.horizontalCenter; text: "YOUR WORLD. YOUR INTELLIGENCE."; color: welcome.t.muted; font.family: welcome.t.fontFamily; font.pixelSize: 10; font.letterSpacing: 2 }
}
