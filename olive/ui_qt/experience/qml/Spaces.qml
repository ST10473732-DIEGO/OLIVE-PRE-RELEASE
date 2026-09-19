import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    clip: true
    ColumnLayout {
        width: Math.min(960, parent.width - 64); x: 32; spacing: 16
        Text { text: "All spaces"; color: tokens.values.text; font.pixelSize: 32; Layout.topMargin: 32 }
        Text { text: "Your work, in one place. Pin the spaces you use most."; color: tokens.values.secondary; font.pixelSize: 16 }
        TextField { Layout.fillWidth: true; placeholderText: "Find a space…"; Accessible.name: "Search spaces"; onTextChanged: experience.filterSpaces(text) }
        Repeater {
            model: experience.spacesModel
            delegate: RowLayout {
                required property string key
                required property string title
                required property string subtitle
                required property bool pinned
                Layout.fillWidth: true
                ActionButton { text: title; Layout.preferredWidth: 200; onClicked: experience.navigate(key) }
                Text { text: subtitle; color: tokens.values.secondary; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 14 }
                ActionButton { text: pinned ? "Unpin" : "Pin"; Accessible.name: text + " " + title; onClicked: experience.togglePin(key) }
            }
        }
        Item { height: 32 }
    }
}
