import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var st: ({ state: "idle" })
    property real now: Date.now() / 1000

    // ---- derived state -------------------------------------------------
    readonly property bool stale: st.state === "run" && st.updated && (now - st.updated) > 900
    readonly property bool finished: (st.state === "done" || st.state === "fail") && st.end && (now - st.end) < 12
    readonly property string mode: stale ? "idle" : (st.state === "run" || st.state === "wait" || finished) ? st.state : "idle"
    readonly property real elapsed: st.start ? Math.max(0, (mode === "done" || mode === "fail" ? st.end : now) - st.start) : 0
    readonly property bool hasPct: mode === "run" && st.pct !== undefined && st.pct !== null
    readonly property real pct: hasPct ? st.pct : 0
    readonly property real etaSec: {
        if (!hasPct || pct >= 100) return -1
        if (st.p0_at !== undefined && st.pct_at > st.p0_at && st.pct - st.p0 >= 2) {
            const rate = (st.pct - st.p0) / (st.pct_at - st.p0_at)
            return Math.max(0, (100 - st.pct) / rate - (now - st.pct_at))
        }
        return -1
    }
    readonly property string etaText: etaSec >= 0 ? "~" + dur(etaSec) + " left" : (hasPct && st.eta ? "~" + st.eta + " left" : "")
    readonly property color accent: mode === "done" ? Kirigami.Theme.positiveTextColor
                                  : mode === "fail" ? Kirigami.Theme.negativeTextColor
                                  : mode === "wait" ? Kirigami.Theme.neutralTextColor
                                  : Kirigami.Theme.textColor
    readonly property string label: mode === "idle" ? "Claude idle" : (st.action || "Working")

    function dur(sec) {
        sec = Math.round(sec)
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h > 0 ? h + "h" + (m < 10 ? "0" : "") + m + "m" : m > 0 ? m + "m" + (s < 10 ? "0" : "") + s + "s" : s + "s"
    }

    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = Date.now() / 1000 }

    P5Support.DataSource {
        engine: "executable"
        interval: 1000
        connectedSources: ["cat \"${XDG_RUNTIME_DIR:-/run/user/1000}/cc-status.json\" 2>/dev/null || echo '{}'"]
        onNewData: (source, data) => {
            try { root.st = JSON.parse(data.stdout) } catch (e) { root.st = ({ state: "idle" }) }
        }
    }

    toolTipMainText: "Claude Code · " + (mode === "idle" ? "idle" : mode === "run" ? "working" : mode === "wait" ? "needs you" : mode === "done" ? "done" : "failed")
    toolTipSubText: mode === "idle" ? "" : label + "\n" + dur(elapsed) + (hasPct ? "  ·  " + Math.round(pct) + "%" : "") + (etaText ? "  ·  " + etaText : "")

    // ---- shared pieces ---------------------------------------------------
    component Dot: Rectangle {
        implicitWidth: Kirigami.Units.gridUnit * 0.6
        implicitHeight: implicitWidth
        radius: width / 2
        color: root.mode === "idle" ? Kirigami.Theme.disabledTextColor : root.accent
        SequentialAnimation on opacity {
            running: root.mode === "run"
            loops: Animation.Infinite
            NumberAnimation { to: 0.3; duration: 700; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
            onRunningChanged: if (!running) parent.opacity = 1
        }
    }
    component Bar: Rectangle {
        property real value: 0
        property bool indeterminate: false
        implicitHeight: Kirigami.Units.gridUnit * 0.28
        radius: height / 2
        color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
        clip: true
        Rectangle {
            visible: !parent.indeterminate
            width: parent.width * Math.max(0, Math.min(100, parent.value)) / 100
            height: parent.height; radius: parent.radius; color: root.accent
            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            id: sweep
            visible: parent.indeterminate
            width: parent.width * 0.3; height: parent.height; radius: parent.radius; color: root.accent
            SequentialAnimation on x {
                running: sweep.visible && root.mode === "run"
                loops: Animation.Infinite
                NumberAnimation { from: -sweep.width; to: sweep.parent.width; duration: 1400; easing.type: Easing.InOutSine }
            }
        }
    }

    // ---- panel ---------------------------------------------------------
    compactRepresentation: MouseArea {
        Layout.minimumWidth: row.implicitWidth + Kirigami.Units.largeSpacing * 2
        onClicked: root.expanded = !root.expanded
        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing * 2
            Dot { Layout.alignment: Qt.AlignVCenter }
            PlasmaComponents.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 16
                text: root.label
                elide: Text.ElideRight
                opacity: root.mode === "idle" ? 0.55 : 1
            }
            Bar {
                visible: root.mode === "run"
                Layout.preferredWidth: Kirigami.Units.gridUnit * 5
                Layout.alignment: Qt.AlignVCenter
                value: root.pct
                indeterminate: !root.hasPct
            }
            PlasmaComponents.Label {
                visible: root.mode !== "idle"
                font.features: { "tnum": 1 }
                opacity: 0.8
                text: (root.hasPct ? Math.round(root.pct) + "%  ·  " : "") + root.dur(root.elapsed) + (root.etaText ? "  ·  " + root.etaText : "")
            }
        }
    }

    // ---- expanded card ---------------------------------------------------
    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        spacing: Kirigami.Units.largeSpacing
        RowLayout {
            spacing: Kirigami.Units.smallSpacing * 2
            Dot { Layout.alignment: Qt.AlignVCenter }
            PlasmaComponents.Label {
                text: root.mode === "idle" ? "Idle" : root.mode === "run" ? "Working" : root.mode === "wait" ? "Needs you" : root.mode === "done" ? "Done" : "Failed"
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            PlasmaComponents.Label { visible: root.mode !== "idle"; text: root.dur(root.elapsed); opacity: 0.8; font.features: { "tnum": 1 } }
        }
        PlasmaComponents.Label {
            Layout.fillWidth: true
            visible: root.mode !== "idle"
            text: root.label
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }
        Bar {
            visible: root.mode === "run"
            Layout.fillWidth: true
            value: root.pct
            indeterminate: !root.hasPct
        }
        PlasmaComponents.Label {
            visible: root.hasPct
            opacity: 0.8
            text: Math.round(root.pct) + "%" + (root.etaText ? "  ·  " + root.etaText : "")
        }
    }
}
