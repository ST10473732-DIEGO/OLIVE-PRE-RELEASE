import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    color: tokens.values.background
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 12
        AbstractButton {
            implicitWidth: 48; implicitHeight: 48
            Accessible.name: "Open activity centre"
            onClicked: experience.showActivity()
            contentItem: Core { }
            background: Rectangle { color: "transparent"; radius: 12; border.color: parent.activeFocus ? tokens.values.accent : "transparent" }
            ToolTip.visible: hovered; ToolTip.text: experience.stateLabel
        }
        ActionButton { text: "OLIVE"; quiet: true; onClicked: experience.navigate("home") }
        Text { text: experience.page === "home" ? "" : experience.pageTitle; color: tokens.values.secondary; font.pixelSize: 14 }
        Item { Layout.fillWidth: true }
        Text { text: experience.activityCount ? experience.activityCount + " active" : experience.stateLabel; color: tokens.values.secondary; font.pixelSize: 13; visible: parent.width > 750 }
        ActionButton { text: "STOP CONTROL"; visible: experience.desktopEnabled; onClicked: experience.stopControl() }
        ActionButton { text: "All spaces"; quiet: true; onClicked: experience.showSpaces() }
        ActionButton { text: "Commands  Ctrl K"; quiet: true; onClicked: experience.palette() }
        ActionButton { text: "Appearance"; quiet: true; onClicked: experience.showAppearance() }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: tokens.values.border }
}
