import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    color: tokens.values.background
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 8; spacing: 4
        ActionButton { text: experience.expanded ? "Collapse" : "☰"; Layout.fillWidth: true; onClicked: experience.toggleNavigation(); Accessible.name: "Expand or collapse workspace navigation" }
        Repeater {
            model: ["home", "chat", "agent", "studio", "research"]
            delegate: AbstractButton {
                required property string modelData
                Layout.fillWidth: true; implicitHeight: 48
                Accessible.name: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                onClicked: experience.navigate(modelData)
                ToolTip.visible: hovered; ToolTip.text: Accessible.name
                background: Rectangle { radius: 12; color: experience.page === modelData || parent.hovered ? tokens.values.elevated : "transparent"; border.color: parent.activeFocus ? tokens.values.accent : "transparent" }
                contentItem: RowLayout {
                    spacing: 12
                    Image { source: experience.assetUrl + "/icons/" + (experience.lightTheme ? "light/" : "dark/") + modelData + ".svg"; Layout.preferredWidth: 24; Layout.preferredHeight: 24; Layout.leftMargin: 12 }
                    Text { visible: experience.expanded; text: modelData.charAt(0).toUpperCase() + modelData.slice(1); color: tokens.values.text; font.pixelSize: 15; Layout.fillWidth: true }
                }
            }
        }
        Item { Layout.fillHeight: true }
        ActionButton { text: experience.expanded ? "All spaces" : "•••"; Accessible.name: "All spaces"; Layout.fillWidth: true; onClicked: experience.showSpaces() }
    }
}
