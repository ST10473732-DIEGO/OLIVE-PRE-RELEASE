import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: card
    property string title
    property string description
    property string feature
    readonly property var t: tokens.values
    hoverEnabled: true
    activeFocusOnTab: true
    Accessible.name: title + ". " + description
    implicitHeight: 156
    background: Rectangle {
        color: card.down ? card.t.border : card.hovered ? card.t.elevated : card.t.surface
        radius: card.t.featureRadius
        border.width: card.activeFocus ? 2 : 1
        border.color: card.activeFocus ? card.t.accent : card.hovered ? card.t.muted : card.t.border
        Behavior on color { ColorAnimation { duration: experience.reducedMotion ? 0 : card.t.hoverMs } }
    }
    contentItem: ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 10
        RowLayout {
            Image { source: experience.assetUrl + "/icons/" + (experience.lightTheme ? "light/" : "dark/") + card.feature + ".svg"; sourceSize: Qt.size(24,24); Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
            Item { Layout.fillWidth: true }
            Text { text: "↗"; color: card.hovered ? card.t.accent : card.t.muted; font.pixelSize: 20 }
        }
        Text { text: card.title; color: card.t.text; font.family: card.t.fontFamily; font.pixelSize: 19; font.weight: Font.DemiBold }
        Text { text: card.description; color: card.t.secondary; font.family: card.t.fontFamily; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.fillHeight: true }
    }
    onClicked: experience.navigate(feature)
}
