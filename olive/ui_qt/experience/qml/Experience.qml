import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    color: tokens.values.background
    Home {
        anchors.fill: parent
        visible: !experience.welcome && !experience.spacesOpen && !experience.galleryOpen
        opacity: experience.welcome ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: experience.reducedMotion ? 0 : tokens.values.enterMs } }
    }
    Spaces { anchors.fill: parent; visible: experience.spacesOpen && !experience.welcome }
    Gallery { anchors.fill: parent; visible: experience.galleryOpen && !experience.welcome }
    Welcome {
        anchors.fill: parent
        enabled: experience.welcome
        visible: opacity > 0
        opacity: experience.welcome ? 1 : 0
        focus: experience.welcome
        onEnterRequested: experience.enter()
        Behavior on opacity { NumberAnimation { duration: experience.reducedMotion ? 0 : tokens.values.enterMs } }
    }
}
