import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: home
    readonly property var t: tokens.values
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ColumnLayout {
        width: Math.min(home.availableWidth - (home.width < 800 ? 40 : 96), home.t.contentWidth)
        x: (home.availableWidth - width) / 2
        spacing: 26
        Item { Layout.preferredHeight: home.height > 760 ? 42 : 14 }
        RowLayout {
            Layout.fillWidth: true
            Text { text: experience.dateLabel.toUpperCase(); color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 11; font.letterSpacing: 1.4 }
            Item { Layout.fillWidth: true }
            Text { text: "LOCAL FIRST"; color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 10; font.letterSpacing: 1.4 }
        }
        ColumnLayout {
            spacing: 8
            Text { text: experience.greeting; color: home.t.text; font.family: home.t.fontFamily; font.pixelSize: home.width < 800 ? 34 : 44; font.weight: Font.DemiBold }
            Text { text: "What would you like to do?"; color: home.t.secondary; font.family: home.t.fontFamily; font.pixelSize: 19 }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: composerBox.implicitHeight + 36
            radius: home.t.featureRadius; color: home.t.surface
            border.width: command.activeFocus ? 2 : 1; border.color: command.activeFocus ? home.t.accent : home.t.border
            ColumnLayout {
                id: composerBox
                anchors.fill: parent; anchors.margins: 18; spacing: 10
                TextField {
                    id: command; objectName: "homeComposer"
                    Layout.fillWidth: true; Layout.preferredHeight: 46
                    placeholderText: "Ask OLIVE anything…"; placeholderTextColor: home.t.muted
                    color: home.t.text; selectionColor: home.t.accent; selectedTextColor: home.t.onAccent
                    font.family: home.t.fontFamily; font.pixelSize: 19; maximumLength: 4000
                    background: Item {}
                    Accessible.name: "Ask OLIVE anything"
                    onAccepted: if (!experience.busy && text.trim().length) { experience.submit(text); text = "" }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { visible: !experience.contextLabel; text: "Conversation, files, projects and your computer"; color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                    ActionButton { visible: experience.contextLabel.length > 0; text: experience.contextLabel; implicitHeight: 34; Layout.fillWidth: true; onClicked: experience.showContext(); Accessible.name: "Inspect selected context: " + experience.contextLabel }
                    ActionButton { text: experience.busy ? "Stop" : "Ask OLIVE  ↑"; primary: !experience.busy; implicitHeight: 38; enabled: experience.busy || command.text.trim().length > 0; onClicked: { if (experience.busy) experience.cancel(); else { experience.submit(command.text); command.text = "" } } }
                }
            }
        }
        Rectangle {
            visible: experience.busy || experience.result.length > 0
            Layout.fillWidth: true; implicitHeight: resultColumn.implicitHeight + 32
            color: home.t.surface; radius: home.t.radius
            ColumnLayout {
                id: resultColumn; anchors.fill: parent; anchors.margins: 16; spacing: 8
                Text { text: experience.busy ? "Working on your request" : "OLIVE"; color: home.t.accent; font.family: home.t.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
                Text { text: experience.understood; textFormat: Text.PlainText; color: home.t.secondary; font.family: home.t.fontFamily; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: experience.result; textFormat: Text.PlainText; visible: text.length > 0; color: home.t.text; font.family: home.t.fontFamily; font.pixelSize: 15; wrapMode: Text.WordWrap; maximumLineCount: 8; elide: Text.ElideRight; Layout.fillWidth: true }
                ActionButton { text: "Continue in Chat"; quiet: true; implicitHeight: 34; onClicked: experience.navigate("chat") }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Make room for your next idea"; color: home.t.secondary; font.family: home.t.fontFamily; font.pixelSize: 13 }
                Item { Layout.fillWidth: true }
                ActionButton { text: "All spaces  →"; quiet: true; implicitHeight: 30; onClicked: experience.showSpaces() }
            }
            GridLayout {
                Layout.fillWidth: true; columns: home.width < 920 ? 2 : 4; columnSpacing: 14; rowSpacing: 14
                FeatureCard { Layout.fillWidth: true; title: "Chat"; description: "Think it through.\nFind the words."; feature: "chat" }
                FeatureCard { Layout.fillWidth: true; title: "Agent"; description: "Turn an objective\ninto approved action."; feature: "agent" }
                FeatureCard { Layout.fillWidth: true; title: "Studio"; description: "Build something\nthat works."; feature: "studio" }
                FeatureCard { Layout.fillWidth: true; title: "Research"; description: "Follow a question.\nKeep the evidence."; feature: "research" }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 28
            ColumnLayout {
                Layout.fillWidth: true; spacing: 12
                Text { text: "Continue"; color: home.t.text; font.family: home.t.fontFamily; font.pixelSize: 19; font.weight: Font.DemiBold }
                Text { visible: recents.count === 0; text: "Your recent conversations and workspaces will appear here."; color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Repeater {
                    id: recents; model: experience.recentModel
                    delegate: AbstractButton {
                        required property string key; required property string title; required property string subtitle
                        Layout.fillWidth: true; implicitHeight: 58; hoverEnabled: true; activeFocusOnTab: true
                        Accessible.name: "Continue " + title
                        background: Rectangle { color: parent.hovered ? home.t.surface : "transparent"; radius: 10; border.width: parent.activeFocus ? 1 : 0; border.color: home.t.accent }
                        contentItem: RowLayout {
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: title; textFormat: Text.PlainText; color: home.t.text; font.family: home.t.fontFamily; font.pixelSize: 14; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: subtitle; color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 11 }
                            }
                            Text { text: "→"; color: home.t.muted; font.pixelSize: 18 }
                        }
                        onClicked: experience.continueItem(key)
                    }
                }
            }
            Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: home.t.border }
            ColumnLayout {
                Layout.preferredWidth: Math.min(260,home.width * 0.25); Layout.alignment: Qt.AlignTop; spacing: 12
                Text { text: "Active work"; color: home.t.text; font.family: home.t.fontFamily; font.pixelSize: 19; font.weight: Font.DemiBold }
                Text { text: experience.activityCount ? experience.activityCount + " active · " + experience.stateLabel : "A little space to focus."; color: home.t.secondary; font.family: home.t.fontFamily; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: experience.activityCount ? "Open activity to inspect progress and approvals." : "Nothing is running. Start when you're ready."; color: home.t.muted; font.family: home.t.fontFamily; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                ActionButton { visible: experience.activityCount > 0; text: "View activity"; quiet: true; onClicked: experience.showActivity() }
            }
        }
        Item { Layout.preferredHeight: 30 }
    }
}
