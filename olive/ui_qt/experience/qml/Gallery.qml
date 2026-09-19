import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    clip: true
    ColumnLayout {
        width: Math.min(1000, parent.width - 64); x: 32; spacing: 24
        Text { text: "Design system / component gallery"; color: tokens.values.text; font.pixelSize: 30; Layout.topMargin: 32 }
        Text { text: "Isolated component examples. These are not active tasks or approvals."; color: tokens.values.secondary; font.pixelSize: 15 }
        RowLayout {
            ActionButton { text: "Primary action"; primary: true }
            ActionButton { text: "Secondary" }
            ActionButton { text: "Quiet"; quiet: true }
            ActionButton { text: "Unavailable"; enabled: false }
            BusyIndicator { running: visible && experience.windowActive && !experience.reducedMotion; implicitWidth: 40; implicitHeight: 40 }
        }
        TextField { Layout.fillWidth: true; placeholderText: "Search or write a request…"; Accessible.name: "Example input" }
        TextField {
            Layout.fillWidth: true; text: "An incomplete value"; Accessible.name: "Example invalid input"
            background: Rectangle { color: tokens.values.surface; radius: 12; border.color: tokens.values.error }
        }
        Text { text: "Example validation: provide a complete value."; color: tokens.values.error; font.pixelSize: 14 }
        TextArea { Layout.fillWidth: true; placeholderText: "Example command composer — no request is executed here"; Accessible.name: "Example composer"; wrapMode: TextEdit.Wrap }
        TabBar {
            Layout.fillWidth: true
            TabButton { text: "Overview" }
            TabButton { text: "Sources" }
            TabButton { text: "Unavailable"; enabled: false }
        }
        RowLayout {
            ActionButton {
                text: "Example menu"; onClicked: exampleMenu.open()
                Menu {
                    id: exampleMenu
                    MenuItem { text: "Inspect example" }
                    MenuItem { text: "Unavailable action"; enabled: false }
                }
            }
            Text { text: "Ready"; color: tokens.values.success; font.pixelSize: 14 }
            Text { text: "Awaiting approval"; color: tokens.values.approval; font.pixelSize: 14 }
            Text { text: "Needs attention"; color: tokens.values.warning; font.pixelSize: 14 }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 64; color: tokens.values.elevated; radius: 12
            RowLayout {
                anchors.fill: parent; anchors.margins: 16
                Text { text: "Selected example row"; color: tokens.values.text; Layout.fillWidth: true }
                Text { text: "Selected"; color: tokens.values.accent }
            }
        }
        ColumnLayout {
            Text { text: "Example task steps"; color: tokens.values.text; font.pixelSize: 18 }
            Text { text: "1  Find the local document · complete"; color: tokens.values.success }
            Text { text: "2  Review the candidate · waiting for approval"; color: tokens.values.approval }
            Text { text: "3  Save the reference · not started"; color: tokens.values.secondary }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 52; color: tokens.values.surface; radius: 12
            Text { anchors.centerIn: parent; text: "Example quiet notification: saved locally."; color: tokens.values.text }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 180; color: tokens.values.surface; radius: 20
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20
                Text { text: "Example approval surface"; color: tokens.values.text; font.pixelSize: 20 }
                Text { text: "To: example@example.test\nMessage: An unsent fixture"; color: tokens.values.secondary }
                Text { text: "example.pdf · fixture attachment"; color: tokens.values.accent }
                RowLayout {
                    ActionButton { text: "Send (disabled example)"; enabled: false; primary: true }
                    ActionButton { text: "Edit example" }
                    ActionButton { text: "Cancel example" }
                }
            }
        }
        RowLayout {
            Repeater {
                model: ["READY", "THINKING", "WORKING", "RESEARCHING", "WAITING_FOR_APPROVAL", "PAUSED", "DEGRADED", "ERROR"]
                delegate: ColumnLayout {
                    required property string modelData
                    Core { phase: modelData; Layout.preferredWidth: 80; Layout.preferredHeight: 80 }
                    Text { text: modelData.replace(/_/g, "\n"); color: tokens.values.secondary; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 130; radius: 20; color: tokens.values.surface
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 24
                Text { text: "A quiet empty state"; color: tokens.values.text; font.pixelSize: 20 }
                Text { text: "Explain what belongs here and offer one useful first action."; color: tokens.values.secondary; font.pixelSize: 15 }
                ActionButton { text: "Begin" }
            }
        }
        RowLayout {
            Text { text: "Appearance"; color: tokens.values.text; font.pixelSize: 16; Layout.fillWidth: true }
            Switch { text: "Light theme"; checked: experience.lightTheme; onToggled: experience.setLightTheme(checked) }
            Switch { text: "Reduced motion"; checked: experience.reducedMotion; onToggled: experience.setReducedMotion(checked) }
        }
    }
}
