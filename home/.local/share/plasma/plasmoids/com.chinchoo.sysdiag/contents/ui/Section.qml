import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: sec
    property string title
    property string value
    property string detail
    property alias values: spark.values
    property alias maxValue: spark.maxValue
    property var extra: null   // optional second series (network upload)

    spacing: 2

    RowLayout {
        Layout.fillWidth: true
        PlasmaComponents.Label {
            text: sec.title
            font.weight: Font.DemiBold
            opacity: 0.7
        }
        Item { Layout.fillWidth: true }
        PlasmaComponents.Label {
            text: sec.value
            font.weight: Font.DemiBold
        }
    }
    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.6
        Rectangle {
            anchors.fill: parent
            radius: Kirigami.Units.smallSpacing
            color: Kirigami.Theme.textColor
            opacity: 0.06
        }
        Spark {
            id: spark
            anchors.fill: parent
            anchors.margins: 3
        }
        Spark {
            anchors.fill: parent
            anchors.margins: 3
            visible: sec.extra !== null
            values: sec.extra || []
            maxValue: spark.maxValue
            lineColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.45)
            fill: false
        }
    }
    PlasmaComponents.Label {
        visible: sec.detail.length > 0
        text: sec.detail
        opacity: 0.55
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }
}
