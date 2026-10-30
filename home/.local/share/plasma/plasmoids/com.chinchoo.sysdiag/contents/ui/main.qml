import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    readonly property int keep: 60
    property var cpuHist: []
    property var memHist: []
    property var rxHist: []
    property var txHist: []
    property var tempHist: []
    property var last: null
    property var cur: ({})
    property real cpu: 0
    property real rxRate: 0
    property real txRate: 0
    readonly property string script: Qt.resolvedUrl("../scripts/stats.py").toString().replace("file://", "")

    function push(arr, v) {
        const a = arr.concat([v])
        return a.length > keep ? a.slice(a.length - keep) : a
    }
    function bytes(n) {
        const u = ["B", "K", "M", "G", "T"]
        let i = 0
        while (n >= 1024 && i < u.length - 1) { n /= 1024; ++i }
        return (n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)) + u[i]
    }
    function gib(kb) { return (kb / 1048576).toFixed(1) + " GiB" }
    function uptime(s) {
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60)
        return h > 0 ? h + "h " + m + "m" : m + "m"
    }
    readonly property real memPct: cur.memTotal ? (cur.memTotal - cur.memAvail) / cur.memTotal * 100 : 0
    readonly property real peakNet: Math.max(10240, Math.max.apply(null, rxHist.concat(txHist).concat([0])))

    P5Support.DataSource {
        engine: "executable"
        interval: 2000
        connectedSources: ["python3 -I '" + root.script + "'"]
        onNewData: (source, data) => {
            let s
            try { s = JSON.parse(data.stdout) } catch (e) { return }
            if (root.last) {
                const dt = s.cpuTotal - root.last.cpuTotal
                root.cpu = dt > 0 ? (1 - (s.cpuIdle - root.last.cpuIdle) / dt) * 100 : 0
                root.rxRate = Math.max(0, (s.rx - root.last.rx) / 2)
                root.txRate = Math.max(0, (s.tx - root.last.tx) / 2)
                root.cpuHist = root.push(root.cpuHist, root.cpu)
                root.memHist = root.push(root.memHist, (s.memTotal - s.memAvail) / s.memTotal * 100)
                root.rxHist = root.push(root.rxHist, root.rxRate)
                root.txHist = root.push(root.txHist, root.txRate)
                root.tempHist = root.push(root.tempHist, s.temp)
            }
            root.last = s
            root.cur = s
        }
    }

    toolTipMainText: "System diagnostics"
    toolTipSubText: "CPU " + cpu.toFixed(0) + "%  ·  RAM " + memPct.toFixed(0) + "%  ·  " + (cur.temp || 0).toFixed(0) + "°C"

    compactRepresentation: MouseArea {
        Layout.minimumWidth: row.implicitWidth + Kirigami.Units.largeSpacing * 2
        onClicked: root.expanded = !root.expanded

        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Kirigami.Units.largeSpacing
            Spark {
                Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                Layout.preferredHeight: Kirigami.Units.gridUnit
                values: root.cpuHist
            }
            PlasmaComponents.Label { text: "CPU " + root.cpu.toFixed(0) + "%" }
            PlasmaComponents.Label { text: "RAM " + root.memPct.toFixed(0) + "%" }
            PlasmaComponents.Label { text: "↓" + root.bytes(root.rxRate) + " ↑" + root.bytes(root.txRate) }
            PlasmaComponents.Label { text: (root.cur.temp || 0).toFixed(0) + "°" }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 21
        Layout.minimumHeight: Kirigami.Units.gridUnit * 30
        spacing: Kirigami.Units.largeSpacing

        Section {
            Layout.fillWidth: true
            title: "CPU"
            value: root.cpu.toFixed(0) + "%"
            detail: "load " + (root.cur.load || "–") + " over 1 min"
            values: root.cpuHist
            maxValue: 100
        }
        Section {
            Layout.fillWidth: true
            title: "Memory"
            value: root.memPct.toFixed(0) + "%"
            detail: root.gib((root.cur.memTotal || 0) - (root.cur.memAvail || 0)) + " of " + root.gib(root.cur.memTotal || 0)
                    + (root.cur.swapTotal ? "  ·  swap " + root.gib(root.cur.swapTotal - root.cur.swapFree) : "")
            values: root.memHist
            maxValue: 100
        }
        Section {
            Layout.fillWidth: true
            title: "Network"
            value: "↓ " + root.bytes(root.rxRate) + "/s   ↑ " + root.bytes(root.txRate) + "/s"
            detail: "bright line: download  ·  dim line: upload  ·  peak " + root.bytes(root.peakNet) + "/s"
            values: root.rxHist
            extra: root.txHist
            maxValue: root.peakNet
        }
        Section {
            Layout.fillWidth: true
            title: "Temperature"
            value: (root.cur.temp || 0).toFixed(0) + " °C"
            detail: ""
            values: root.tempHist
            maxValue: 100
        }

        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [
                    { k: "Disk", v: root.cur.diskTotal ? (root.cur.diskUsed / root.cur.diskTotal * 100).toFixed(0) + "%" : "–" },
                    { k: "Battery", v: root.cur.bat >= 0 ? root.cur.bat + "%" + (root.cur.batStatus === "Charging" ? " ⚡" : "") : "–" },
                    { k: "Uptime", v: root.uptime(root.cur.uptime || 0) }
                ]
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PlasmaComponents.Label {
                        text: modelData.v
                        font.weight: Font.DemiBold
                        Layout.alignment: Qt.AlignHCenter
                    }
                    PlasmaComponents.Label {
                        text: modelData.k
                        opacity: 0.55
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
        }
    }
}
