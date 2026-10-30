import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var items: []
    readonly property string script: Qt.resolvedUrl("../scripts/recent.py").toString().replace("file://", "")

    toolTipMainText: "Pick up where you left off"
    toolTipSubText: items.length ? items[0].name : ""

    Plasmoid.icon: "document-open-recent"

    P5Support.DataSource {
        id: loader
        engine: "executable"
        interval: 30000
        connectedSources: ["python3 -I '" + root.script + "'"]
        onNewData: (source, data) => {
            try { root.items = JSON.parse(data.stdout) } catch (e) {}
        }
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => disconnectSource(source)
        function run(cmd) { connectSource(cmd) }
    }

    readonly property string pinScript: Qt.resolvedUrl("../scripts/pin.py").toString().replace("file://", "")
    function togglePin(path) {
        exec.run("python3 -I '" + pinScript + "' " + q(path))
        loader.disconnectSource(loader.connectedSources[0])
        loader.connectSource("python3 -I '" + script + "'")
    }
    function q(s) { return "'" + s.replace(/'/g, "'\\''") + "'" }
    function launch(cmd) {
        exec.run("setsid -f " + cmd + " >/dev/null 2>&1")
        root.expanded = false
    }
    function ago(ts) {
        const m = Math.round((Date.now() / 1000 - ts) / 60)
        if (m < 60) return Math.max(m, 1) + " min ago"
        if (m < 1440) return Math.round(m / 60) + " h ago"
        return Math.round(m / 1440) + " d ago"
    }

    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.preferredHeight: Kirigami.Units.gridUnit * 26
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Heading {
            level: 3
            text: "Pick up where you left off"
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Kirigami.Units.smallSpacing
            model: root.items

            delegate: Rectangle {
                width: ListView.view.width
                height: card.implicitHeight + Kirigami.Units.largeSpacing * 2
                radius: Kirigami.Units.smallSpacing * 2
                color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, (index === 0 || modelData.pinned) ? 0.12 : 0.06)
                border.width: index === 0 ? 1 : 0
                border.color: Kirigami.Theme.textColor

                ColumnLayout {
                    id: card
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        PlasmaComponents.Label {
                            text: (modelData.pinned ? "📌 " : "") + modelData.name
                            font.weight: Font.Bold
                        }
                        PlasmaComponents.Label {
                            visible: modelData.branch.length > 0
                            text: " " + modelData.branch + (modelData.dirty ? " ●" : "")
                            opacity: 0.6
                        }
                        Item { Layout.fillWidth: true }
                        PlasmaComponents.Label {
                            text: (index === 0 ? "last · " : "") + root.ago(modelData.ts)
                            opacity: 0.55
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                    }
                    PlasmaComponents.Label {
                        Layout.fillWidth: true
                        text: modelData.path.replace(/^\/home\/[^/]+/, "~")
                        opacity: 0.55
                        elide: Text.ElideMiddle
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                    PlasmaComponents.Label {
                        Layout.fillWidth: true
                        visible: modelData.prompt.length > 0
                        text: "“" + modelData.prompt + "”"
                        opacity: 0.75
                        elide: Text.ElideRight
                        font.italic: true
                    }
                    RowLayout {
                        Layout.topMargin: Kirigami.Units.smallSpacing
                        PlasmaComponents.Button {
                            visible: modelData.session.length > 0
                            icon.name: "utilities-terminal"
                            text: "Resume Claude"
                            onClicked: root.launch("konsole --workdir " + root.q(modelData.path)
                                                   + " -e claude --resume " + modelData.session)
                        }
                        PlasmaComponents.Button {
                            icon.name: "utilities-terminal"
                            text: "Terminal"
                            onClicked: root.launch("konsole --workdir " + root.q(modelData.path))
                        }
                        PlasmaComponents.Button {
                            icon.name: modelData.pinned ? "window-unpin" : "window-pin"
                            text: modelData.pinned ? "Unpin" : "Pin"
                            onClicked: root.togglePin(modelData.path)
                        }
                        PlasmaComponents.Button {
                            icon.name: "document-edit"
                            text: "Zed"
                            onClicked: root.launch("zed " + root.q(modelData.path))
                        }
                    }
                }
            }
        }
    }
}
