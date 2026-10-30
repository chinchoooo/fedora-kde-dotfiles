import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property bool running: false
    property bool playing: false
    property string artist: ""
    property string track: ""

    preferredRepresentation: fullRepresentation

    P5Support.DataSource {
        id: poll
        engine: "executable"
        interval: 1500
        connectedSources: ["playerctl -p spotify metadata --format '{{status}}\t{{artist}}\t{{title}}' 2>/dev/null"]
        onNewData: (source, data) => {
            const out = (data.stdout || "").trim()
            root.running = out.length > 0
            const f = out.split("\t")
            root.playing = f[0] === "Playing"
            root.artist = f[1] || ""
            root.track = f[2] || ""
        }
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => disconnectSource(source)
        function run(cmd) { connectSource(cmd) }
    }

    function control(verb) {
        if (!running) {
            exec.run("setsid -f flatpak run com.spotify.Client --minimized >/dev/null 2>&1")
        } else {
            exec.run("playerctl -p spotify " + verb)
        }
    }

    fullRepresentation: RowLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 14
        Layout.preferredWidth: Kirigami.Units.gridUnit * 17
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.ToolButton {
            icon.name: "media-skip-backward"
            enabled: root.running
            onClicked: root.control("previous")
        }
        PlasmaComponents.ToolButton {
            icon.name: root.playing ? "media-playback-pause" : "media-playback-start"
            onClicked: root.control("play-pause")
        }
        PlasmaComponents.ToolButton {
            icon.name: "media-skip-forward"
            enabled: root.running
            onClicked: root.control("next")
        }
        PlasmaComponents.Label {
            Layout.fillWidth: true
            elide: Text.ElideRight
            opacity: root.running ? 1 : 0.6
            text: root.running
                  ? (root.artist ? root.artist + " — " : "") + root.track
                  : "Spotify — click ▶ to start"
        }
    }
}
